"""The ``signals`` config section."""

from __future__ import annotations

from pydantic import BaseModel, Field

from odsod_daemon.components.signals.contract import Platform as PlatformName


class SignalsConfig(BaseModel):
    cdp_ports: list[int] = Field(default_factory=lambda: [9222])
    platforms: list[PlatformName] = Field(default_factory=lambda: ["meet", "teams"])
    tab_poll_s: float = Field(default=2.0, gt=0)
    speaking_poll_ms: int = Field(default=250, gt=0)
    start_samples: int = Field(default=2, ge=1)
    start_window_ms: int = Field(default=1500, gt=0)
    stop_grace_ms: int = Field(default=2000, ge=0)
    toggles_required: int = Field(default=3, ge=1)
    end_grace_s: float = Field(default=10.0, ge=0)
    participants_stable_s: float = Field(default=5.0, ge=0)
    no_indicator_after_s: float = Field(default=300.0, gt=0)

    @property
    def start_window_s(self) -> float:
        return self.start_window_ms / 1000

    @property
    def stop_grace_s(self) -> float:
        return self.stop_grace_ms / 1000

    @property
    def speaking_poll_s(self) -> float:
        return self.speaking_poll_ms / 1000
