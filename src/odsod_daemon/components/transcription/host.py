"""Speech inference fault policy, shared by the two inference workers."""

import hashlib
import json
from collections.abc import Awaitable, Callable

import httpx

from odsod_daemon.lib import clock, healthfile, paths


class InputFailed(Exception):
    def __init__(self, error: Exception, attempts: int):
        super().__init__(str(error).splitlines()[0])
        self.attempts = attempts


class HostUnavailable(RuntimeError):
    """Drain stopped with work still pending."""


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def fault_kind(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {429, 502, 503, 504}:
            return "host"
        return "input" if status >= 500 else "reject"
    if isinstance(
        error,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadError,
            httpx.WriteError,
            httpx.RemoteProtocolError,
            httpx.PoolTimeout,
        ),
    ):
        return "host"
    if isinstance(error, httpx.TimeoutException):
        return "input"
    return "reject"


def health(key: str, *, down: bool, since: str | None = None) -> None:
    # Reload for every mutation: another speech worker may have changed its key.
    file = healthfile.HealthFile(paths.roots().run / "health/pipeline.json", "pipeline")
    if down:
        file.set(
            "inference-unreachable",
            f"{key} inference unavailable",
            key=key,
            since=since,
        )
    else:
        file.clear("inference-unreachable", key=key)
    file.rewrite()


class Host:
    def __init__(self, key: str):
        self.key = key
        self.down_at: float | None = None
        self.since: str | None = None
        self.delay = 2.0

    async def call[T](
        self,
        call: Callable[[], Awaitable[T]],
        *,
        attempts: int,
        once: bool,
        raw_on_host: bool = False,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> tuple[T, int]:
        tried = 0
        while True:
            if before_request is not None:
                await before_request()
            try:
                result = await call()
            except Exception as error:
                kind = fault_kind(error)
                if kind == "host":
                    if self.down_at is None:
                        self.down_at = clock.monotonic()
                        self.since = clock.iso()
                    elapsed = clock.monotonic() - self.down_at
                    if elapsed >= 60:
                        health(self.key, down=True, since=self.since)
                    if raw_on_host:
                        raise HostUnavailable(str(error)) from error
                    if once and elapsed >= 60:
                        raise HostUnavailable(
                            f"{self.key}: host unavailable; work remains pending"
                        ) from error
                    delay = (
                        min(self.delay, max(0, 60 - elapsed)) if once else self.delay
                    )
                    await clock.sleep(delay)
                    self.delay = min(30, self.delay * 2)
                    continue
                tried += 1
                if kind == "reject" or tried >= attempts:
                    raise InputFailed(error, tried) from error
                await clock.sleep(min(8, 0.5 * 2 ** (tried - 1)))
                continue
            self.down_at = None
            self.delay = 2
            health(self.key, down=False)
            return result, tried + 1
