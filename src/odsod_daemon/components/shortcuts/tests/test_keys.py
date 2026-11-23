import pytest

from odsod_daemon.components.shortcuts import keys


@pytest.mark.parametrize(
    ("sequence", "code"),
    [
        ("Meta+C", 0x10000000 | ord("C")),
        ("Meta+c", 0x10000000 | ord("C")),
        ("Meta+1", 0x10000000 | ord("1")),
        ("Meta+-", 0x10000000 | ord("-")),
        ("Meta+'", 0x10000000 | ord("'")),
        ("Meta+;", 0x10000000 | ord(";")),
        ("Meta+Backspace", 0x10000000 | 0x01000003),
        ("Ctrl+Alt+Shift+F12", 0x04000000 | 0x08000000 | 0x02000000 | 0x0100003B),
        ("Space", 0x20),
    ],
)
def test_parse(sequence: str, code: int):
    assert keys.parse(sequence) == code


@pytest.mark.parametrize("sequence", ["Meta+Hyper", "Meta+é", "Super+C", ""])
def test_unknown_key_raises(sequence: str):
    with pytest.raises(ValueError, match="unknown key"):
        keys.parse(sequence)
