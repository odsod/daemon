"""The pipeline service: speech, signals, transcript, interactions, publishing."""

from __future__ import annotations

from odsod_daemon.components import (  # noqa: F401
    cleanup,
    interactions,
    publish,
    segmentation,
    signals,
    transcript,
    transcription,
)
from odsod_daemon.services.runner import ServiceSpec

NAME = "pipeline"

COMPONENTS = [
    segmentation,
    transcription,
    cleanup,
    signals,
    transcript,
    interactions,
    publish,
]

SERVICE = ServiceSpec(NAME, COMPONENTS)
