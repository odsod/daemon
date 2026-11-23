from __future__ import annotations

from pathlib import Path

import pytest

from odsod_daemon.components.keys import contract

COMPONENT = Path(__file__).parents[1]

MESSAGES: list[tuple[contract.Message, str]] = [
    (
        contract.Start(time="2026-11-23T19:40:05.747Z"),
        "start 2026-11-23T19:40:05.747Z\n",
    ),
    (contract.Stop(time="2026-11-23T19:40:07.001Z"), "stop 2026-11-23T19:40:07.001Z\n"),
    (
        contract.Cancel(time="2026-11-23T19:40:08.120Z"),
        "cancel 2026-11-23T19:40:08.120Z\n",
    ),
    (contract.Paste(), "paste\n"),
    (contract.Pasted(), "pasted\n"),
    (contract.PasteFailed(reason="modifier-held"), "paste-failed modifier-held\n"),
]


@pytest.mark.parametrize(("message", "line"), MESSAGES)
def test_format_writes_the_wire_line(message: contract.Message, line: str) -> None:
    assert contract.format(message) == line


@pytest.mark.parametrize(("message", "line"), MESSAGES)
def test_parse_reads_the_wire_line(message: contract.Message, line: str) -> None:
    assert contract.parse(line) == message
    assert contract.parse(line.rstrip("\n")) == message
    assert contract.parse(line.replace("\n", "\r\n")) == message


@pytest.mark.parametrize(("message", "line"), MESSAGES)
def test_round_trip(message: contract.Message, line: str) -> None:
    assert contract.parse(contract.format(message)) == message
    assert contract.format(contract.parse(line)) == line


@pytest.mark.parametrize(
    "line",
    [
        "",
        "nope",
        "start",
        "start ",
        "start a b",
        "stop",
        "cancel",
        "paste now",
        "pasted now",
        "paste-failed",
        "paste-failed ",
    ],
)
def test_parse_rejects_bad_lines(line: str) -> None:
    with pytest.raises(ValueError):
        contract.parse(line)


def test_format_rejects_an_empty_reason() -> None:
    with pytest.raises(ValueError):
        contract.format(contract.PasteFailed(reason=""))


def test_package_data_names_exist() -> None:
    assert contract.C_SOURCE_DIR == "c"
    assert contract.SYSTEM_UNIT == "odsod-daemon-keys.service"
    assert contract.SOCKET_PATH == "/run/odsod-daemon-keys/dictation.sock"
    assert (COMPONENT / contract.C_SOURCE_DIR).is_dir()
    for source in ("state.h", "state.c", "io.c", "replay.c"):
        assert (COMPONENT / contract.C_SOURCE_DIR / source).is_file()
