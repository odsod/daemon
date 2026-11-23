"""Suppress exact phantom phrases and ordered glossary echoes."""

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
