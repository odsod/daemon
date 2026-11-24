"""Suppress exact phantom phrases and ordered glossary echoes; drop fillers."""

import re


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def phantom(text: str, phrases: list[str]) -> bool:
    return any(tokens(text) == tokens(phrase) for phrase in phrases)


def glossary_echo(text: str, glossary: list[str]) -> bool:
    words = tokens(text)
    if not words:
        return False
    cursor = count = covered = 0
    for term in glossary:
        target = tokens(term)
        if not target:
            continue
        for start in range(cursor, len(words) - len(target) + 1):
            if words[start : start + len(target)] == target:
                count += 1
                covered += len(target)
                cursor = start + len(target)
                break
    return count >= 3 and covered / len(words) >= 0.7


# English hesitation sounds only. Parakeet writes them; whisper's prompt hid them.
_FILLER = re.compile(r"\s*\b(?:u+h+|u+h*m+|e+r+m+)\b,?", re.IGNORECASE)


def fillers(text: str) -> str:
    """Drop "uh", "um" and "erm" from dictated English, keep the rest as is."""
    out = _FILLER.sub("", text)
    out = re.sub(r"\s+([,.?!;:])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip().lstrip(",").strip()
    if not re.search(r"\w", out):
        return ""
    if text.lstrip()[:1].isupper():
        out = out[0].upper() + out[1:]
    return out
