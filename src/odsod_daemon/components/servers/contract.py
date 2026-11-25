"""The inference config section and the server units, for install and control.

Install renders one unit per server on a host with inference enabled.
Control expects those units on that host only.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from odsod_daemon.components.servers import pins


class Whisper(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = Field(default=8178, ge=1, le=65535)
    extra_args: list[str] = []


class Llama(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int = Field(default=8179, ge=1, le=65535)
    extra_args: list[str] = []


class Inference(BaseModel):
    """Config section ``inference``. Only the inference host enables it."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    whisper: Whisper = Field(default_factory=Whisper)
    llama: Llama = Field(default_factory=Llama)


@dataclass(frozen=True)
class Server:
    name: str
    unit: str
    # Relative to the state root.
    binary: str
    model: str
    # After --model <model> --port <port>, before the config's extra_args.
    args: tuple[str, ...]


SERVERS: tuple[Server, ...] = (
    Server(
        name="whisper",
        unit="odsod-daemon-whisper.service",
        binary=pins.BUILDS["whisper"].binary,
        model=f"models/{pins.MODELS['whisper'].name}",
        args=(
            "--host",
            "0.0.0.0",
            "--language",
            "auto",
            "--suppress-nst",
            "--convert",
            "--inference-path",
            "/v1/audio/transcriptions",
        ),
    ),
    Server(
        name="llama",
        unit="odsod-daemon-llama.service",
        binary=pins.BUILDS["llama"].binary,
        model=f"models/{pins.MODELS['llama'].name}",
        args=(
            "--host",
            "0.0.0.0",
            "--ctx-size",
            "32768",
            "--n-gpu-layers",
            "99",
            "--flash-attn",
            "on",
            "--cache-type-k",
            "q8_0",
            "--cache-type-v",
            "q8_0",
            "--reasoning",
            "off",
            "--parallel",
            "4",
            # An explicit slot count turns the shared cache off. One shared
            # cache for the 4 slots is a safe default (ADR-0023).
            "--kv-unified",
            "--spec-type",
            "ngram-simple",
            "--spec-ngram-simple-size-n",
            "2",
            "--spec-ngram-simple-size-m",
            "32",
        ),
    ),
)

# The units of the machine repo that ran the servers before ADR-0023. Two
# owners would fight for the same ports and GPU memory.
LEGACY_UNITS = ("llama-server.service", "whisper-server.service")
CUTOVER = (
    "systemctl --user disable --now llama-server whisper-server",
    "odsodctl install",
)
ROLLBACK = (
    "systemctl --user disable --now odsod-daemon-llama odsod-daemon-whisper",
    "systemctl --user enable --now llama-server whisper-server",
)
