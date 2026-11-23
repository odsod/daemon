"""Token overlap of two texts.

Each caller keeps its own threshold. The function makes no decision.
"""

from __future__ import annotations

import re
from collections import Counter

_NON_WORD = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")

MIN_TOKENS = 3


def normalize(text: str) -> str:
    lowered = text.lower()
    replaced = _NON_WORD.sub(" ", lowered)
    return _SPACES.sub(" ", replaced).strip()


def overlap(a: str, b: str) -> float:
    """Token overlap of two texts, 0.0 to 1.0.

    0.0 when the shorter text has fewer than 3 tokens, so a short reply such
    as "Yes" never counts as an echo. 1.0 when one text holds the other.
    """
    left = normalize(a)
    right = normalize(b)
    left_tokens = left.split()
    right_tokens = right.split()
    shorter = min(len(left_tokens), len(right_tokens))
    if shorter < MIN_TOKENS:
        return 0.0
    if left == right or left in right or right in left:
        return 1.0
    left_counts = Counter(left_tokens)
    right_counts = Counter(right_tokens)
    common = sum((left_counts & right_counts).values())
    return common / shorter
