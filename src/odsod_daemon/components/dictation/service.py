"""Run holds, connection policy and ordered text delivery beside one another."""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from odsod_daemon.components.dictation import delivery, gate, mute, notify
from odsod_daemon.components.dictation.config import DictationConfig
from odsod_daemon.components.dictation.contract import (
    DictationUtterance,
    KeysState,
    StatusDocument,
)
from odsod_daemon.components.dictation.keys_client import KeysClient
from odsod_daemon.components.dictation.loop import Loop
from odsod_daemon.components.keys.contract import SOCKET_PATH
from odsod_daemon.lib import (
    audio,
    clock,
    config,
    documents,
    healthfile,
    inference,
    paths,
    power,
    streams,
    systemd,
)

LOG = logging.getLogger(__name__)


def moment(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def stamp(seconds: float) -> str:
    return clock.iso(moment(seconds))


async def text_for(state: Path, hold: DictationUtterance, deadline: float) -> dict:
    """Follow both possible UTC day files, including records already written."""
    records: asyncio.Queue[dict] = asyncio.Queue()

    async def follow(day):
        async for record in streams.follow(
            streams.day_path(state / "text", day), start_at_end=False, scan_s=0.05
        ):
            if record.get("input") == hold.id:
                records.put_nowait(record)

    days = {clock.parse_iso(hold.release).date(), moment(deadline).date()}
    async with (
        clock.timeout(max(0, deadline - clock.wall())),
        asyncio.TaskGroup() as group,
    ):
        tasks = [group.create_task(follow(day)) for day in days]
        record = await records.get()
        for task in tasks:
            task.cancel()
    return record


class Session:
    def __init__(
        self,
        settings: DictationConfig,
        *,
        socket_path: str = SOCKET_PATH,
        units: systemd.UnitStateSource | None = None,
    ):
        self.settings = settings
        self.roots = paths.roots().ensure()
        self.socket_path = socket_path
        self.units = units if units is not None else systemd.DBusUnitStates()
        self.loop = Loop()
        self.mute = mute.Mute(self.roots.run / "muted.json")
        self.keys: KeysState = "no-socket"
        self.client: KeysClient | None = None
        self.queue: asyncio.Queue[
            tuple[DictationUtterance, dict[str, float], asyncio.Task[dict | None]]
        ] = asyncio.Queue()
        self.idle = asyncio.Event()
        self.idle.set()
        self.waiters: set[asyncio.Task] = set()
        self.previous_status: dict = {}
        self.stale_until = 0.0
        self.fault("keys-socket-missing", False)

    def fault(self, code: str, active: bool) -> None:
        # Reload so future session components keep their own fault codes.
        health = healthfile.HealthFile(
            self.roots.run / "health/session.json", "session"
        )
        if active:
            health.set(code, code.replace("-", " "))
        else:
            health.clear(code)
        health.rewrite()

    def status(self) -> None:
        document = StatusDocument(
            mode="dictating" if not self.idle.is_set() else "idle",
            since=clock.iso(),
            keys=self.keys,
            audio_start=stamp(self.loop.start) if not self.idle.is_set() else None,
        )
        value = document.model_dump(exclude_none=True)
        change = {k: v for k, v in value.items() if k != "since"}
        if change != self.previous_status:
            documents.write_json(self.roots.run / "status.json", value)
            self.previous_status = change

    async def unmute(self) -> None:
        """Fail open: a failed unmute must not stop the hold or the service."""
        try:
            await self.mute.stop()
        except OSError, TimeoutError, ValueError:
            LOG.exception("unmute failed")
            self.fault("mute-failed", True)

    async def startup(self) -> None:
        stale = bool(mute.read(self.mute.path).streams)
        await self.unmute()
        self.fault("stale-mutes-cleared", stale)
        if stale:
            self.stale_until = clock.monotonic() + 600
        self.status()

    async def actions(self, kind: str, at: float = 0) -> None:
        for action in self.loop.event(kind, at):
            if action == "mute":
                self.idle.clear()
                self.fault("stale-mutes-cleared", False)
                self.stale_until = 0
                self.fault("mute-failed", not await self.mute.start())
            elif action == "dictating":
                self.status()
            elif action == "unmute":
                await self.unmute()
            elif action == "cover":
                try:
                    await audio.wait_until(
                        self.roots.state,
                        "mic",
                        moment(self.loop.end),
                        timeout_s=2,
                        poll_s=0.02,
                    )
                except TimeoutError:
                    await notify.send("dictation failed")
                    await self.actions("failed")
                else:
                    self.timing = {
                        "release": 0,
                        "coverage": (clock.wall() - self.loop.release) * 1000,
                    }
                    await self.actions("covered")
            elif action == "append":
                self.hold = DictationUtterance(
                    ts=clock.iso(),
                    id="dic-"
                    + stamp(self.loop.start).replace("-", "").replace(":", ""),
                    start=stamp(self.loop.start),
                    end=stamp(self.loop.end),
                    press=stamp(self.loop.press),
                    release=stamp(self.loop.release),
                    muted=self.mute.count,
                )
                streams.append(
                    streams.day_path(
                        self.roots.state / "utterances/dictation",
                        clock.utc_now().date(),
                    ),
                    self.hold.model_dump(),
                )
                self.timing["append"] = (clock.wall() - self.loop.release) * 1000
            elif action == "idle":
                self.idle.set()
                self.status()
            elif action == "queue":
                task = asyncio.create_task(self.wait_text(self.hold, self.timing))
                self.waiters.add(task)
                task.add_done_callback(self.waiters.discard)
                self.queue.put_nowait((self.hold, self.timing, task))

    async def wait_text(
        self, hold: DictationUtterance, timing: dict[str, float]
    ) -> dict | None:
        deadline = (
            clock.parse_iso(hold.release).timestamp() + self.settings.text_timeout_s
        )
        try:
            text = await text_for(self.roots.state, hold, deadline)
        except TimeoutError:
            await notify.send("dictation failed")
            return None
        timing["text"] = (
            clock.wall() - clock.parse_iso(hold.release).timestamp()
        ) * 1000
        if clock.wall() > deadline or text["outcome"] in {"failed", "expired"}:
            await notify.send("dictation failed")
            return None
        return text

    async def deliver_one(
        self,
        hold: DictationUtterance,
        timing: dict[str, float],
        task: asyncio.Task[dict | None],
    ) -> None:
        try:
            text = await task
            if text is None or text["outcome"] == "empty" or not text["text"]:
                return
            await self.idle.wait()
            release = clock.parse_iso(hold.release).timestamp()

            async def request():
                await self.idle.wait()
                timing["paste"] = (clock.wall() - release) * 1000
                result = self.client is not None and await self.client.paste()
                if result:
                    timing["pasted"] = (clock.wall() - release) * 1000
                return result

            await delivery.paste(text["text"], request, self.settings.restore_delay_ms)
        finally:
            LOG.info("dictation timing id=%s offsets_ms=%s", hold.id, timing)
            self.queue.task_done()

    async def deliver(self) -> None:
        while True:
            await self.deliver_one(*await self.queue.get())

    async def receive(self, client: KeysClient) -> None:
        try:
            while True:
                try:
                    async with clock.timeout(0.05):
                        message = await client.events.get()
                except TimeoutError:
                    await self.actions("tick", clock.wall())
                    continue
                if message is None:
                    break
                await self.actions(
                    message.kind, clock.parse_iso(message.time).timestamp()
                )
        finally:
            await client.close()
            if self.client is client:
                self.client = None
                self.keys = "no-socket"
                await self.actions("disconnected")
                self.status()

    async def connections(self) -> None:
        reachable = False
        probe_at = 0.0
        missing_at: float | None = None
        retry_at = 0.0
        backoff = 1.0
        consumer: asyncio.Task | None = None
        try:
            async with asyncio.TaskGroup() as group:
                while True:
                    now = clock.monotonic()
                    if self.stale_until and now >= self.stale_until:
                        self.fault("stale-mutes-cleared", False)
                        self.stale_until = 0
                    url = config.load_common(self.roots).inference.whisper_url
                    if now >= probe_at:
                        reachable = await inference.reachable(url, timeout_s=1)
                        probe_at = now + self.settings.probe_interval_s
                    unit = await self.units.get("odsod-daemon-capture.service")
                    reason = gate.reason(
                        capture=unit is not None and unit.active_state == "active",
                        reachable=reachable,
                        mains=power.on_mains(),
                        loopback=inference.is_loopback(url),
                    )
                    exists = Path(self.socket_path).exists()
                    if not exists:
                        missing_at = now if missing_at is None else missing_at
                    elif reason != "connected" and missing_at is not None:
                        missing_at = None
                        self.fault("keys-socket-missing", False)
                    if gate.may_disconnect(self.loop.state):
                        if self.client is not None and (
                            reason != "connected" or not exists
                        ):
                            await self.client.close()
                            if consumer is not None:
                                await consumer
                        if (
                            self.client is None
                            and reason == "connected"
                            and now >= retry_at
                        ):
                            try:
                                self.client = await KeysClient.connect(self.socket_path)
                            except OSError, TimeoutError:
                                missing_at = now if missing_at is None else missing_at
                                retry_at = now + backoff
                                backoff = min(10, backoff * 2)
                            else:
                                group.create_task(self.client.read())
                                consumer = group.create_task(self.receive(self.client))
                                await self.actions("connected")
                                missing_at = None
                                backoff = 1
                                self.fault("keys-socket-missing", False)
                        self.keys = (
                            "connected"
                            if self.client is not None
                            else "no-socket"
                            if reason == "connected"
                            else reason
                        )
                        self.status()
                    if missing_at is not None and now - missing_at >= 10:
                        self.fault("keys-socket-missing", True)
                    healthfile.HealthFile(
                        self.roots.run / "health/session.json", "session"
                    ).rewrite()
                    delay = 2.0
                    if self.client is None and reason == "connected" and retry_at > now:
                        delay = min(delay, retry_at - now)
                    if missing_at is not None and now < missing_at + 10:
                        delay = min(delay, missing_at + 10 - now)
                    await clock.sleep(delay)
        finally:
            if self.client is not None:
                await self.client.close()

    async def run(self, *, once: bool = False) -> None:
        logging.basicConfig(level=logging.INFO)
        await self.startup()
        if once:
            return
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self.deliver())
                group.create_task(self.connections())
        finally:
            for task in self.waiters:
                task.cancel()
            await asyncio.gather(*self.waiters, return_exceptions=True)
            if isinstance(self.units, systemd.DBusUnitStates):
                await self.units.close()
