"""Build replay.c and compare each sequence with its expected output."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

COMPONENT = Path(__file__).parents[1]
C_DIR = COMPONENT / "c"
TESTDATA = Path(__file__).parent / "testdata"
GCC = shutil.which("gcc")

pytestmark = pytest.mark.skipif(GCC is None, reason="gcc not installed")

SEQUENCES = sorted(TESTDATA.glob("*.seq"))


@pytest.fixture(scope="module")
def replay(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert GCC is not None
    binary = tmp_path_factory.mktemp("keys") / "replay"
    result = subprocess.run(
        [
            GCC,
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o",
            str(binary),
            str(C_DIR / "replay.c"),
            str(C_DIR / "state.c"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return binary


def expected_output(sequence: Path) -> list[str]:
    lines: list[str] = []
    for raw in sequence.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and " out " in f" {line} ":
            lines.append(line)
    return lines


def test_every_sequence_has_an_input() -> None:
    assert SEQUENCES
    for sequence in SEQUENCES:
        text = sequence.read_text(encoding="utf-8")
        assert " in " in f" {text} ", sequence.name


@pytest.mark.parametrize("sequence", SEQUENCES, ids=lambda path: path.stem)
def test_sequence(sequence: Path, replay: Path) -> None:
    result = subprocess.run(
        [str(replay), str(sequence)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected_output(sequence)
