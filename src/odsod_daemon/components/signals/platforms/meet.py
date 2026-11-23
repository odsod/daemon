"""Google Meet: host, path code, tab title, tile DOM."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from odsod_daemon.components.signals.platforms.base import (
    MeetingRef,
    Platform,
    PlatformName,
    strip_title,
    url_without_query,
)

HOST = "meet.google.com"
_CODE = re.compile(r"^/([a-z]{3}-[a-z]{4}-[a-z]{3})/?$")
_PREFIXES = (
    "Meet \u2013 ",
    "Meet - ",
    "Meet \u2014 ",
    "Google Meet \u2013 ",
    "Google Meet - ",
)
_SUFFIXES: tuple[str, ...] = ()


class Meet(Platform):
    name: PlatformName = "meet"

    def meeting(self, url: str, title: str) -> MeetingRef | None:
        parts = urlsplit(url)
        if parts.hostname != HOST:
            return None
        match = _CODE.fullmatch(parts.path)
        if match is None:
            return None
        code = match.group(1)
        cleaned = strip_title(title, _PREFIXES, _SUFFIXES)
        return MeetingRef(self.name, code, cleaned or code, url_without_query(url))
