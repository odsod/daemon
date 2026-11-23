"""A fake CDP server: ``/json/list`` plus a WebSocket that answers evaluate.

The script is a list of values per phase. Each evaluate call takes the next
value of its phase, and repeats the last value after the list ends.
"""

from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from websockets.asyncio.server import Server, ServerConnection, serve

from odsod_daemon.components.signals.platforms.meet import Meet
from odsod_daemon.components.signals.platforms.teams import Teams

SNAPSHOT_EXPRESSIONS = frozenset({Meet().snapshot_js(), Teams().snapshot_js()})


class FakeCdp:
    def __init__(self) -> None:
        self.tabs: list[dict[str, str]] = []
        self.snapshot_values: list[str] = []
        self.poll_values: list[str] = []
        self.expressions: list[str] = []
        self.http_requests = 0
        self.error_next = 0
        self.drop_next = 0
        self._snapshot_index = 0
        self._poll_index = 0
        self._ws_port = 0
        self._http: ThreadingHTTPServer | None = None
        self._server: Server | None = None
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        self._server = await serve(self._handle_ws, "127.0.0.1", 0)
        self._ws_port = self._server.sockets[0].getsockname()[1]
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake.http_requests += 1
                if self.path != "/json/list":
                    self.send_error(404)
                    return
                body = json.dumps(fake.tabs).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return None

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._http.daemon_threads = True
        self._thread = threading.Thread(target=self._http.serve_forever, daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @property
    def port(self) -> int:
        assert self._http is not None
        return int(self._http.server_address[1])

    def script(
        self,
        *,
        snapshots: list[str] | None = None,
        polls: list[str] | None = None,
    ) -> None:
        if snapshots is not None:
            self.snapshot_values = snapshots
            self._snapshot_index = 0
        if polls is not None:
            self.poll_values = polls
            self._poll_index = 0

    def add_tab(self, title: str, url: str, *, kind: str = "page") -> None:
        self.tabs.append(
            {
                "title": title,
                "url": url,
                "type": kind,
                "webSocketDebuggerUrl": (
                    f"ws://127.0.0.1:{self._ws_port}/devtools/page/{len(self.tabs) + 1}"
                ),
            }
        )

    async def _handle_ws(self, websocket: ServerConnection) -> None:
        async for message in websocket:
            request = json.loads(message)
            expression = str(request["params"]["expression"])
            self.expressions.append(expression)
            if self.drop_next > 0:
                self.drop_next -= 1
                await websocket.close()
                return
            if self.error_next > 0:
                self.error_next -= 1
                await websocket.send(
                    json.dumps(
                        {"id": request["id"], "error": {"message": "script error"}}
                    )
                )
                continue
            await websocket.send(
                json.dumps(
                    {
                        "id": request["id"],
                        "result": {
                            "result": {
                                "type": "string",
                                "value": self._value(expression),
                            }
                        },
                    }
                )
            )

    def _value(self, expression: str) -> str:
        if expression in SNAPSHOT_EXPRESSIONS:
            index = self._snapshot_index
            self._snapshot_index += 1
            values = self.snapshot_values
        else:
            index = self._poll_index
            self._poll_index += 1
            values = self.poll_values
        if not values:
            return "[]"
        return values[min(index, len(values) - 1)]


@pytest.fixture
async def fake_cdp() -> AsyncIterator[FakeCdp]:
    fake = FakeCdp()
    await fake.start()
    try:
        yield fake
    finally:
        await fake.stop()
