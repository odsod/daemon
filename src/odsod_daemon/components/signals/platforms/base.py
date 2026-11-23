"""Shared platform parts: URL rules, titles, codes and JS results.

A platform is stateless. It answers three questions: is this tab a meeting,
what is the meeting, and which JavaScript reads the page.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import dataclass
from importlib import resources
from urllib.parse import urlsplit, urlunsplit

from odsod_daemon.components.signals.contract import Platform as PlatformName

SLUG_MAX = 40
_SLUG_SEP = re.compile(r"[^a-z0-9]+")
_CLASS_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class MeetingRef:
    platform: PlatformName
    code: str
    title: str
    url: str

    @property
    def key(self) -> tuple[str, str]:
        """The meeting identity; the title and URL may change mid-call."""
        return (self.platform, self.code)


def same_meeting(left: MeetingRef | None, right: MeetingRef | None) -> bool:
    """Two refs name the same meeting, even when a tab title changed."""
    if left is None or right is None:
        return left is None and right is None
    return left.key == right.key


@dataclass(frozen=True)
class SnapshotTile:
    name: str
    classes: frozenset[str]


@dataclass(frozen=True)
class PollTile:
    name: str
    speaking: bool


class Platform:
    """One meeting platform: URL rule, meeting code, JavaScript, parsing."""

    name: PlatformName

    def matches(self, url: str) -> bool:
        return self.meeting(url, "") is not None

    def meeting(self, url: str, title: str) -> MeetingRef | None:
        raise NotImplementedError

    def snapshot_js(self) -> str:
        return _js(f"{self.name}.snapshot.js")

    def poll_js(self, speaking_class: str) -> str:
        if not _CLASS_NAME.fullmatch(speaking_class):
            raise ValueError(f"invalid CSS class: {speaking_class!r}")
        return _js(f"{self.name}.poll.js").replace("__SPEAKING_CLASS__", speaking_class)

    def parse_snapshot(self, value: str) -> list[SnapshotTile]:
        data = _decode(value)
        tiles: list[SnapshotTile] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            raw = item.get("classes")
            values = raw if isinstance(raw, list) else []
            classes = frozenset(
                text for text in (str(value).strip() for value in values) if text
            )
            tiles.append(SnapshotTile(name, classes))
        return tiles

    def parse_poll(self, value: str) -> list[PollTile]:
        data = _decode(value)
        tiles: list[PollTile] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                continue
            tiles.append(PollTile(name, bool(item.get("speaking"))))
        return tiles


@functools.cache
def _js(name: str) -> str:
    directory = resources.files("odsod_daemon.components.signals.platforms").joinpath(
        "js"
    )
    return directory.joinpath(name).read_text(encoding="utf-8").strip()


def _decode(value: str) -> list[object]:
    if not value:
        return []
    data = json.loads(value)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array")
    return data


def url_without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def strip_title(
    title: str, prefixes: tuple[str, ...], suffixes: tuple[str, ...]
) -> str:
    """Remove the platform name around the tab title."""
    cleaned = title.strip()
    lowered = cleaned.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip(" -\u2013\u2014|")
            break
    lowered = cleaned.lower()
    for suffix in suffixes:
        if lowered.endswith(suffix.lower()):
            cleaned = cleaned[: -len(suffix)].strip(" -\u2013\u2014|")
            break
    return cleaned


def slug(text: str) -> str:
    """ASCII, lowercase, ``-`` between words, at most 40 characters."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = decomposed.encode("ascii", "ignore").decode("ascii")
    return _SLUG_SEP.sub("-", plain.lower()).strip("-")[:SLUG_MAX].strip("-")
