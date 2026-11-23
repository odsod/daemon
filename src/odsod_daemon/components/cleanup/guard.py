"""Clean model formatting and reject loss of length or numbers."""

import re
import unicodedata
from collections import Counter
from typing import Literal


def clean(text: str) -> str:
    text = re.sub(
        r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL | re.IGNORECASE
    )
    return "".join(c for c in text if unicodedata.category(c) != "Cf").strip()


def reason(source: str, reply: str) -> Literal["guard-length", "guard-number"] | None:
    if not 0.5 * len(source) <= len(reply) <= 2 * len(source):
        return "guard-length"

    def numbers(s: str):
        return Counter(re.findall(r"\d+(?:[.,]\d+)*", s))

    if numbers(source) - numbers(reply):
        return "guard-number"
    return None
