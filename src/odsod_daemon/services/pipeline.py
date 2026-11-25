"""The pipeline service: speech, signals, transcript, interactions, publishing.

On the base, the host components also run per satellite host root. A
satellite runs only its dictation, signals and sync (ADR-0024).
"""

from __future__ import annotations

from odsod_daemon.components import (
    cleanup,
    interactions,
    parakeet,
    publish,
    segmentation,
    signals,
    sync,
    transcript,
    transcription,
)
from odsod_daemon.services.runner import ServiceSpec

NAME = "pipeline"

COMPONENTS = [
    segmentation,
    transcription,
    cleanup,
    parakeet,
    signals,
    transcript,
    interactions,
    publish,
]

PER_HOST = [segmentation, transcription, cleanup, transcript, interactions, publish]

SATELLITE = [transcription, cleanup, signals, sync]

SERVICE = ServiceSpec(NAME, COMPONENTS, per_host=PER_HOST, satellite=SATELLITE)
