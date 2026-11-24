"""The signals loop: poll CDP, feed the pure parts, write records.

Only this module writes ``events/signals/``. Only the health fault goes to
``run/health/pipeline.json``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from odsod_daemon.components.signals import cdp
from odsod_daemon.components.signals.config import SignalsConfig
from odsod_daemon.components.signals.contract import (
    MeetingEnd,
    MeetingStart,
    Participants,
    Speaking,
)
from odsod_daemon.components.signals.debounce import SpeakerDebounce
from odsod_daemon.components.signals.discovery import Discovery
from odsod_daemon.components.signals.meeting import End, Meeting, Start
from odsod_daemon.components.signals.platforms import PLATFORMS
from odsod_daemon.components.signals.platforms.base import (
    MeetingRef,
    Platform,
    PollTile,
    same_meeting,
)
from odsod_daemon.lib import clock, healthfile, paths, streams

log = logging.getLogger(__name__)

SERVICE = "pipeline"
NO_INDICATOR = "no-speaking-indicator"
MAX_EVALUATE_FAILURES = 10

Record = MeetingStart | MeetingEnd | Participants | Speaking


@dataclass(frozen=True)
class _Resume:
    ref: MeetingRef
    participants: tuple[str, ...]
    speaking: tuple[str, ...]


@dataclass(frozen=True)
class _Eval:
    tiles: tuple[PollTile, ...]
    speaking_known: bool


def load_resume(directory: Path, day: date) -> _Resume | None:
    """The open meeting of a previous process, with its last sets."""
    open_ref: MeetingRef | None = None
    participants: tuple[str, ...] = ()
    speaking: tuple[str, ...] = ()
    for record in streams.read_days(directory, day - timedelta(days=1), day):
        kind = record.get("kind")
        if kind == "meeting-start":
            try:
                start = MeetingStart.model_validate(record)
            except ValidationError:
                continue
            open_ref = MeetingRef(
                start.platform, start.code, start.title, start.url or ""
            )
            participants = ()
            speaking = ()
        elif kind == "meeting-end":
            open_ref = None
            participants = ()
            speaking = ()
        elif open_ref is not None:
            try:
                if kind == "participants":
                    names = Participants.model_validate(record).names
                elif kind == "speaking":
                    names = Speaking.model_validate(record).names
                else:
                    continue
            except ValidationError:
                continue
            ref = MeetingRef(open_ref.platform, open_ref.code, "", "")
            if not _same(record, ref):
                continue
            if kind == "participants":
                participants = tuple(sorted(names))
            else:
                speaking = tuple(sorted(names))
    if open_ref is None:
        return None
    return _Resume(open_ref, participants, speaking)


def _same(record: dict[str, object], ref: MeetingRef) -> bool:
    return record.get("platform") == ref.platform and record.get("code") == ref.code


def _iso(epoch_s: float) -> str:
    return clock.iso(datetime.fromtimestamp(epoch_s, UTC))


class Collector:
    def __init__(
        self,
        config: SignalsConfig,
        *,
        roots: paths.Roots | None = None,
        platforms: Sequence[Platform] = PLATFORMS,
    ) -> None:
        self.config = config
        self.roots = (roots or paths.roots()).ensure()
        self.platforms: dict[str, Platform] = {
            platform.name: platform
            for platform in platforms
            if platform.name in config.platforms
        }
        self.stream_dir = self.roots.state / "events" / "signals"
        self.health_path = self.roots.run / "health" / f"{SERVICE}.json"

        self._meeting = Meeting(end_grace_s=config.end_grace_s)
        self._debounce = SpeakerDebounce(
            start_samples=config.start_samples,
            start_window_s=config.start_window_s,
            stop_grace_s=config.stop_grace_s,
            poll_s=config.speaking_poll_s,
        )
        self._started_at = 0.0
        self._resume: _Resume | None = None
        self._candidate: tuple[MeetingRef, str] | None = None
        self._session: cdp.Session | None = None
        self._ws_url: str | None = None
        self._ref: MeetingRef | None = None
        self._classes: dict[str, str] = {}
        self._discovery: Discovery | None = None
        self._failures = 0
        self._last_participants: tuple[str, ...] = ()
        self._pending_participants: tuple[str, ...] | None = None
        self._pending_since = 0.0
        self._last_speaking: tuple[str, ...] = ()
        self._discovery_since: float | None = None
        self._speaker_at: float | None = None
        self._fault = False
        self._unreachable = False

    @property
    def meeting(self) -> MeetingRef | None:
        return self._meeting.active

    async def start(self, now: float | None = None) -> None:
        moment = clock.wall() if now is None else now
        self._started_at = moment
        day = datetime.fromtimestamp(moment, UTC).date()
        self._resume = load_resume(self.stream_dir, day)
        health = healthfile.HealthFile(self.health_path, SERVICE)
        if health.clear(NO_INDICATOR):
            health.rewrite()
        self._fault = False

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._ws_url = None

    async def run(self, *, once: bool = False) -> None:
        await self.start()
        try:
            if once:
                await self.tab_tick()
                if self._meeting.active is not None:
                    await self.speaking_tick()
                return
            while True:
                await self.tab_tick()
                deadline = clock.monotonic() + self.config.tab_poll_s
                while (
                    self._meeting.active is not None
                    and self._session is not None
                    and clock.monotonic() < deadline
                ):
                    await clock.sleep(self.config.speaking_poll_s)
                    await self.speaking_tick()
                await clock.sleep(max(0.0, deadline - clock.monotonic()))
        finally:
            await self.close()

    async def tab_tick(self, now: float | None = None) -> None:
        moment = clock.wall() if now is None else now
        candidate = await self._find_candidate()
        ref = candidate[0] if candidate is not None else None
        if not same_meeting(ref, self._ref):
            self._reset_tab()
        self._ref = ref
        self._candidate = candidate
        evaluated = (
            await self._evaluate(moment, connect=True)
            if candidate is not None
            else None
        )
        if self._resume is not None:
            self._settle_resume(moment, candidate, evaluated)

        tiles = None if evaluated is None else len(evaluated.tiles)
        events = self._meeting.observe(moment, ref, tiles)
        self._on_events(events)
        if self._meeting.active is None:
            return
        if evaluated is not None:
            self._observe_tiles(moment, evaluated)
        self._check_indicator(moment, tiles)

    async def speaking_tick(self, now: float | None = None) -> None:
        moment = clock.wall() if now is None else now
        if self._meeting.active is None or self._candidate is None:
            return
        evaluated = await self._evaluate(moment, connect=False)
        if evaluated is None:
            return
        self._observe_tiles(moment, evaluated)
        self._check_indicator(moment, len(evaluated.tiles))

    async def _find_candidate(self) -> tuple[MeetingRef, str] | None:
        for port in dict.fromkeys(self.config.cdp_ports):
            try:
                tabs = await cdp.list_tabs(port)
            except cdp.CdpError as error:
                if not self._unreachable:
                    self._unreachable = True
                    log.warning("no CDP on port %d: %s", port, error)
                continue
            if self._unreachable:
                self._unreachable = False
                log.info("CDP reachable on port %d", port)
            for tab in tabs:
                if tab.type != "page" or not tab.websocket_url:
                    continue
                for platform in self.platforms.values():
                    ref = platform.meeting(tab.url, tab.title)
                    if ref is not None:
                        return ref, tab.websocket_url
        return None

    async def _evaluate(self, now: float, *, connect: bool) -> _Eval | None:
        if self._candidate is None:
            return None
        ref, ws_url = self._candidate
        platform = self.platforms.get(ref.platform)
        if platform is None:
            return None
        if self._session is None or self._ws_url != ws_url:
            if not connect:
                return None
            await self.close()
            try:
                self._session = await cdp.Session.open(ws_url)
            except cdp.CdpError as error:
                log.debug("cannot open tab socket: %s", error)
                return None
            self._ws_url = ws_url
        session = self._session
        assert session is not None

        speaking_class = self._classes.get(ref.platform)
        try:
            expression = (
                None if speaking_class is None else platform.poll_js(speaking_class)
            )
        except ValueError:
            # Not a valid CSS identifier: drop it and rediscover now.
            self._classes.pop(ref.platform, None)
            self._discovery = None
            return None
        try:
            if expression is None:
                return await self._discover(session, ref, platform, now)
            value = await session.evaluate(expression)
            tiles = tuple(platform.parse_poll(value))
        except ValueError:
            self._failed(ref)
            return None
        except cdp.CdpError as error:
            await self.close()
            self._failed(ref)
            log.debug("evaluate failed: %s", error)
            return None
        self._failures = 0
        return _Eval(tuple(PollTile(t.name, t.speaking) for t in tiles), True)

    async def _discover(
        self,
        session: cdp.Session,
        ref: MeetingRef,
        platform: Platform,
        now: float,
    ) -> _Eval:
        discovery = self._discovery or Discovery(self.config.toggles_required)
        value = await session.evaluate(platform.snapshot_js())
        result = discovery.observe(platform.parse_snapshot(value))
        self._failures = 0
        if result.confirmed is None:
            self._discovery = discovery
            return _Eval(
                tuple(PollTile(tile.name, False) for tile in result.tiles), False
            )
        confirmed = result.confirmed
        self._classes[ref.platform] = confirmed
        self._discovery = None
        self._discovery_since = None
        self._speaker_at = now
        return _Eval(
            tuple(
                PollTile(tile.name, confirmed in tile.classes) for tile in result.tiles
            ),
            True,
        )

    def _failed(self, ref: MeetingRef) -> None:
        self._failures += 1
        if self._failures < MAX_EVALUATE_FAILURES:
            return
        self._classes.pop(ref.platform, None)
        self._discovery = None
        self._failures = 0

    def _reset_tab(self) -> None:
        self._discovery = None
        self._failures = 0

    def _settle_resume(
        self,
        now: float,
        candidate: tuple[MeetingRef, str] | None,
        evaluated: _Eval | None,
    ) -> None:
        resume, self._resume = self._resume, None
        assert resume is not None
        if (
            candidate is not None
            and same_meeting(candidate[0], resume.ref)
            and evaluated is not None
            and evaluated.tiles
        ):
            self._meeting.resume(resume.ref)
            self._debounce.resume(resume.speaking, now)
            self._last_participants = resume.participants
            self._last_speaking = resume.speaking
            self._speaker_at = now
            return
        if resume.speaking:
            self._write(
                Speaking(
                    ts=clock.iso(),
                    platform=resume.ref.platform,
                    code=resume.ref.code,
                    names=[],
                    at=_iso(self._started_at),
                )
            )
        self._write(
            MeetingEnd(
                ts=clock.iso(),
                platform=resume.ref.platform,
                code=resume.ref.code,
                at=_iso(self._started_at),
                cause="restart",
            )
        )

    def _on_events(self, events: Sequence[Start | End]) -> None:
        for event in events:
            if isinstance(event, End):
                self._flush_speaking(event.ref, event.at)
                self._debounce.reset()
                self._last_speaking = ()
                self._last_participants = ()
                self._pending_participants = None
                self._discovery_since = None
                self._speaker_at = None
                self._clear_fault()
                self._write(
                    MeetingEnd(
                        ts=clock.iso(),
                        platform=event.ref.platform,
                        code=event.ref.code,
                        at=_iso(event.at),
                        cause=event.cause,
                    )
                )
            elif isinstance(event, Start):
                self._debounce.reset()
                self._last_speaking = ()
                self._last_participants = ()
                self._pending_participants = None
                self._discovery_since = None
                self._speaker_at = event.at
                self._write(
                    MeetingStart(
                        ts=clock.iso(),
                        platform=event.ref.platform,
                        code=event.ref.code,
                        title=event.ref.title,
                        url=event.ref.url,
                        at=_iso(event.at),
                    )
                )

    def _flush_speaking(self, ref: MeetingRef, at: float) -> None:
        if not self._last_speaking:
            return
        self._write(
            Speaking(
                ts=clock.iso(),
                platform=ref.platform,
                code=ref.code,
                names=[],
                at=_iso(at),
            )
        )

    def _observe_tiles(self, now: float, evaluated: _Eval) -> None:
        if evaluated.speaking_known:
            before = self._debounce.active
            changes = self._debounce.observe(
                now, [tile.name for tile in evaluated.tiles if tile.speaking]
            )
            after = self._debounce.active
            if after != before:
                at = max(change.at for change in changes) if changes else now
                self._write_speaking(at, after)
                if after:
                    self._speaker_at = now
                    self._clear_fault()
        self._observe_participants(now, {tile.name for tile in evaluated.tiles})

    def _observe_participants(self, now: float, names: set[str]) -> None:
        ref = self._meeting.active
        if ref is None:
            return
        current = tuple(sorted(names))
        if current == self._last_participants:
            self._pending_participants = None
            return
        if current != self._pending_participants:
            self._pending_participants = current
            self._pending_since = now
            return
        if now - self._pending_since < self.config.participants_stable_s:
            return
        self._last_participants = current
        self._pending_participants = None
        self._write(
            Participants(
                ts=clock.iso(),
                platform=ref.platform,
                code=ref.code,
                names=list(current),
            )
        )

    def _write_speaking(self, at: float, names: frozenset[str]) -> None:
        ref = self._meeting.active
        if ref is None:
            return
        self._last_speaking = tuple(sorted(names))
        self._write(
            Speaking(
                ts=clock.iso(),
                platform=ref.platform,
                code=ref.code,
                names=list(self._last_speaking),
                at=_iso(at),
            )
        )

    def _check_indicator(self, now: float, tiles: int | None) -> None:
        ref = self._meeting.active
        if ref is None or tiles is None:
            return
        if ref.platform not in self._classes:
            if tiles < 2:
                self._discovery_since = None
                return
            if self._discovery_since is None:
                self._discovery_since = now
            elif now - self._discovery_since >= self.config.no_indicator_after_s:
                self._set_fault(ref.platform, now)
            return

        self._discovery_since = None
        if tiles < 2:
            self._speaker_at = None
            return
        if self._debounce.active:
            self._speaker_at = now
            return
        if self._speaker_at is None:
            self._speaker_at = now
        elif now - self._speaker_at >= self.config.no_indicator_after_s:
            self._classes.pop(ref.platform, None)
            self._discovery = None
            self._speaker_at = now
            self._discovery_since = now
            self._set_fault(ref.platform, now)

    def _remote_speech(self, now: float) -> bool:
        """True if the sys channel had speech in the last window.

        Without it the meeting is just silent, as when everyone works, so a
        missing indicator says nothing about a UI change."""
        since = datetime.fromtimestamp(now - self.config.no_indicator_after_s, UTC)
        records = streams.read_days(
            self.roots.state / "utterances" / "ambient",
            since.date(),
            clock.utc_now().date(),
        )
        return any(
            r.get("kind") == "utterance"
            and r.get("channel") == "sys"
            and clock.parse_iso(r["end"]) >= since
            for r in records
        )

    def _set_fault(self, platform: str, now: float) -> None:
        if self._fault or not self._remote_speech(now):
            return
        self._fault = True
        health = healthfile.HealthFile(self.health_path, SERVICE)
        health.set(
            NO_INDICATOR,
            "Meeting tab open, no speaking indicator for 5 min "
            f"(`{platform}` UI change?)",
        )
        health.rewrite()

    def _clear_fault(self) -> None:
        if not self._fault:
            return
        self._fault = False
        health = healthfile.HealthFile(self.health_path, SERVICE)
        health.clear(NO_INDICATOR)
        health.rewrite()

    def _write(self, record: Record) -> None:
        day = clock.utc_now().date()
        streams.append(
            streams.day_path(self.stream_dir, day), record.model_dump(mode="json")
        )
