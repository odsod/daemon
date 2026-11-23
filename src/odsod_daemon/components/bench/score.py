"""Scoring: normalization, WER, glossary hits and latency percentiles."""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Sequence

KEEP = {"'", "-"}


def normalize(text: str) -> str:
    """NFC, lower case, punctuation to space, collapsed spaces."""
    lowered = unicodedata.normalize("NFC", text).lower()
    kept = [char if char.isalnum() or char in KEEP else " " for char in lowered]
    return " ".join("".join(kept).split())


def _jiwer():
    import jiwer

    return jiwer


def word_error_rate(
    references: Sequence[str], hypotheses: Sequence[str]
) -> float | None:
    """Corpus WER over normalized pairs. None with no reference words."""
    pairs = [
        (normalize(reference), normalize(hypothesis))
        for reference, hypothesis in zip(references, hypotheses, strict=True)
        if normalize(reference)
    ]
    if not pairs:
        return None
    refs, hyps = zip(*pairs, strict=True)
    return float(_jiwer().wer(list(refs), list(hyps)))


def glossary_hits(
    references: Sequence[str],
    outputs: Sequence[str],
    terms: Iterable[str],
) -> tuple[int, int]:
    """Terms of the reference that the output spells the same. (hits, total)."""
    normalized_terms = [normalize(term) for term in terms]
    normalized_terms = [term for term in normalized_terms if term]
    hits = 0
    total = 0
    for reference, output in zip(references, outputs, strict=True):
        reference_text = normalize(reference)
        output_text = normalize(output)
        for term in normalized_terms:
            if term in reference_text:
                total += 1
                if term in output_text:
                    hits += 1
    return hits, total


def percentile(values: Sequence[float], quantile: float) -> float | None:
    """Nearest-rank percentile. None for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]
