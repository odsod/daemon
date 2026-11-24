"""Clean model formatting and reject loss of length, numbers or words."""

import re
import unicodedata
from collections import Counter
from typing import Literal


def clean(text: str) -> str:
    text = re.sub(
        r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL | re.IGNORECASE
    )
    return "".join(c for c in text if unicodedata.category(c) != "Cf").strip()


# Share of reply words that must come from the source. A translation shares
# almost none; filler removal and spelling fixes keep most of them.
MIN_OVERLAP = 0.5


def reason(
    source: str, reply: str
) -> Literal["guard-length", "guard-number", "guard-overlap"] | None:
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
    return None
