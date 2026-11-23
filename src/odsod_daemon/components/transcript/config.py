"""Transcript settings and the host's system time zone."""

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field


class TranscriptConfig(BaseModel):
    echo_threshold: float = Field(default=0.6, ge=0, le=1)
    echo_tolerance_s: float = Field(default=2, ge=0)
    echo_hold_max_s: float = Field(default=120, ge=0)
    gap_min_s: float = Field(default=60, ge=0)
    restart_max_s: float = Field(default=300, ge=0)
    finish_settle_s: float = Field(default=60, ge=0)
    finish_cap_h: float = Field(default=48, gt=0)


def local_zone() -> ZoneInfo:
    path = Path("/etc/localtime")
    resolved = str(path.resolve())
    if "/zoneinfo/" in resolved:
        return ZoneInfo(resolved.split("/zoneinfo/", 1)[1])
    with path.open("rb") as handle:
        return ZoneInfo.from_file(handle, key="local")
