"""Chrome DevTools Protocol: the tab list over HTTP, evaluate over WebSocket.

Only ``127.0.0.1`` is used for the tab list. A tab's own WebSocket URL comes
from Chrome and points at the same host.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from odsod_daemon.lib import clock

TAB_LIST_TIMEOUT_S = 5.0
EVALUATE_TIMEOUT_S = 10.0


class CdpError(RuntimeError):
    """The browser did not answer, or answered with an error."""


@dataclass(frozen=True)
class Tab:
    title: str
    url: str
    type: str
    websocket_url: str


async def list_tabs(port: int, *, timeout_s: float = TAB_LIST_TIMEOUT_S) -> list[Tab]:
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        # Plain HTTP on 127.0.0.1: no CA file to read, so a reinstall that
        # replaces the package under a running pipeline cannot crash a poll.
        async with httpx.AsyncClient(timeout=timeout_s, verify=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise CdpError(f"{url}: {error}") from error
    if not isinstance(data, list):
        raise CdpError(f"{url}: expected a list of targets")
    tabs: list[Tab] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tabs.append(
            Tab(
                title=str(item.get("title") or ""),
                url=str(item.get("url") or ""),
                type=str(item.get("type") or ""),
                websocket_url=str(item.get("webSocketDebuggerUrl") or ""),
            )
        )
    return tabs


class Session:
    """One open tab WebSocket, reused across polls."""

    def __init__(self, connection: ClientConnection) -> None:
        self._connection = connection
        self._next_id = 0

    @classmethod
    async def open(
        cls, websocket_url: str, *, timeout_s: float = EVALUATE_TIMEOUT_S
    ) -> Session:
        try:
            connection = await connect(
                websocket_url, open_timeout=timeout_s, max_size=None
            )
        except (OSError, WebSocketException, TimeoutError) as error:
            raise CdpError(f"{websocket_url}: {error}") from error
        return cls(connection)

    async def evaluate(
        self, expression: str, *, timeout_s: float = EVALUATE_TIMEOUT_S
    ) -> str:
        self._next_id += 1
        request_id = self._next_id
        request = {
            "id": request_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }
        try:
            await self._connection.send(json.dumps(request))
            while True:
                async with clock.timeout(timeout_s):
                    message = await self._connection.recv()
                data = json.loads(message)
                if not isinstance(data, dict) or data.get("id") != request_id:
                    continue
                return _value(data, expression)
        except (
            OSError,
            WebSocketException,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            raise CdpError(f"Runtime.evaluate: {error}") from error

    async def close(self) -> None:
        await self._connection.close()


def _value(data: dict[str, object], expression: str) -> str:
    if "error" in data:
        raise CdpError(f"Runtime.evaluate: {data['error']}")
    result = data.get("result")
    if not isinstance(result, dict):
        raise CdpError(f"Runtime.evaluate: bad result for {expression[:40]!r}")
    if result.get("exceptionDetails"):
        raise CdpError(f"Runtime.evaluate: {result['exceptionDetails']}")
    inner = result.get("result")
    if not isinstance(inner, dict):
        raise CdpError("Runtime.evaluate: no result value")
    value = inner.get("value")
    if isinstance(value, str):
        return value
    return json.dumps(value)
