from __future__ import annotations

import io

from pydantic import BaseModel

from odsod_daemon.lib import cli


class Result(BaseModel):
    name: str
    count: int


def test_render_text() -> None:
    model = Result(name="ok", count=2)
    assert cli.render(model, as_json=False, text=lambda value: value.name) == "ok"


def test_render_json() -> None:
    model = Result(name="ok", count=2)
    rendered = cli.render(model, as_json=True, text=lambda value: value.name)
    assert '"name": "ok"' in rendered
    assert '"count": 2' in rendered


def test_emit_writes_one_line() -> None:
    stream = io.StringIO()
    cli.emit(
        Result(name="ok", count=2),
        as_json=False,
        text=lambda value: value.name,
        stream=stream,
    )
    assert stream.getvalue() == "ok\n"
