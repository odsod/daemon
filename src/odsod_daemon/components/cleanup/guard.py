"""Clean model formatting and reject loss of length, numbers or words."""

import functools
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Literal


def clean(text: str) -> str:
    text = re.sub(
        r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL | re.IGNORECASE
    )
    return "".join(c for c in text if unicodedata.category(c) != "Cf").strip()


# Share of reply words that must come from the source. A translation shares
# almost none; filler removal and spelling fixes keep most of them.
MIN_OVERLAP = 0.5


# An English word list from the host. Missing list: the English guard is off.
WORDS = Path("/usr/share/dict/words")
# Shorter words are often Swedish too ("till", "bara").
MIN_ENGLISH = 5
WORD = re.compile(r"[^\W\d_][^\W\d_-]*(?:-[^\W\d_]+)*")


@functools.cache
def english() -> frozenset[str]:
    try:
        return frozenset(w.strip().lower() for w in WORDS.open(encoding="utf-8"))
    except OSError:
        return frozenset()


def translated(source: str, reply: str) -> bool:
    """A Swedish line lost an English word: cleanup translated it."""
    kept = {w.lower() for w in WORD.findall(reply)}
    for word in WORD.findall(source):
        low = word.lower()
        if (
            len(word) >= MIN_ENGLISH
            and word.isascii()
            and low in english()
            and low not in kept
            and not any(low in k or k in low for k in kept if len(k) >= 4)
        ):
            return True
    return False


def reason(
    source: str, reply: str, language: str | None = None
) -> Literal["guard-length", "guard-number", "guard-overlap", "guard-english"] | None:
    if not 0.5 * len(source) <= len(reply) <= 2 * len(source):
        return "guard-length"

    def numbers(s: str):
        return Counter(re.findall(r"\d+(?:[.,]\d+)*", s))

    if numbers(source) - numbers(reply):
        return "guard-number"

    def words(s: str) -> set[str]:
        return set(re.findall(r"\w+", s.lower()))

    said = words(reply)
    if said and len(said & words(source)) < MIN_OVERLAP * len(said):
        return "guard-overlap"
    if language == "sv" and translated(source, reply):
        return "guard-english"
    return None
