"""Microsoft Teams: host, thread ID or title slug, tile DOM."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from odsod_daemon.components.signals.platforms.base import (
    MeetingRef,
    Platform,
    PlatformName,
    slug,
    strip_title,
    url_without_query,
)

HOSTS = frozenset({"teams.microsoft.com", "teams.live.com"})
_THREAD = re.compile(r"19:[^@\s&/]+@thread\.[a-z0-9]+")
_PREFIXES = (
    "Microsoft Teams \u2013 ",
    "Microsoft Teams - ",
    "Teams \u2013 ",
    "Teams - ",
)
_SUFFIXES = (" | Microsoft Teams", " - Microsoft Teams", " | Teams", " - Teams")


class Teams(Platform):
    name: PlatformName = "teams"

    def meeting(self, url: str, title: str) -> MeetingRef | None:
        parts = urlsplit(url)
        if parts.hostname not in HOSTS:
            return None
        cleaned = strip_title(title, _PREFIXES, _SUFFIXES)
        thread = _THREAD.search(unquote(url))
        if thread is not None:
            code = thread.group(0)
        else:
            code = f"title:{slug(cleaned) or 'untitled'}"
        return MeetingRef(self.name, code, cleaned or code, url_without_query(url))
