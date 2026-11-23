"""Parse a key sequence such as ``Meta+C`` to a Qt key code."""

from __future__ import annotations

MODIFIERS = {
    "Meta": 0x10000000,
    "Ctrl": 0x04000000,
    "Alt": 0x08000000,
    "Shift": 0x02000000,
}

KEYS: dict[str, int] = {
    "Backspace": 0x01000003,
    "Tab": 0x01000001,
    "Return": 0x01000004,
    "Escape": 0x01000000,
    "Space": 0x20,
    "Delete": 0x01000007,
    "Insert": 0x01000006,
    "Home": 0x01000010,
    "End": 0x01000011,
    "PageUp": 0x01000016,
    "PageDown": 0x01000017,
    "Left": 0x01000012,
    "Up": 0x01000013,
    "Right": 0x01000014,
    "Down": 0x01000015,
    "Print": 0x01000009,
    "Plus": 0x2B,
    **{f"F{n}": 0x01000030 + n - 1 for n in range(1, 13)},
    **{char: ord(char) for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    **{char: ord(char) for char in "-=[]\\;',./`"},
}


def parse(sequence: str) -> int:
    """Return the Qt key code of ``sequence``. Raise ``ValueError`` if unknown."""
    code = 0
    for part in sequence.split("+"):
        if part in MODIFIERS:
            code |= MODIFIERS[part]
            continue
        key = part.upper() if len(part) == 1 and part.isalpha() else part
        if key not in KEYS:
            raise ValueError(f"unknown key {part!r} in {sequence!r}")
        code |= KEYS[key]
    return code
