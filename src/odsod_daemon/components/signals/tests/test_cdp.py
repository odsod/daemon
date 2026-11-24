import asyncio
import json
import ssl

from odsod_daemon.components.signals import cdp


async def test_tab_list_reads_no_ca_file(monkeypatch):
    """Live laptop 2026-11-24: a reinstall removed the CA file under the
    running pipeline, and the next tab poll crashed it. Plain HTTP on
    127.0.0.1 needs no certificates."""
    body = json.dumps(
        [{"title": "t", "url": "u", "type": "page", "webSocketDebuggerUrl": "w"}]
    ).encode()

    async def serve(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    def gone(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(ssl, "create_default_context", gone)
    try:
        tabs = await cdp.list_tabs(port)
    finally:
        server.close()
        await server.wait_closed()
    assert [t.title for t in tabs] == ["t"]
