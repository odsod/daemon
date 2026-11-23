"""Check speech presence without cutting dictation into smaller requests."""

from odsod_daemon.components.segmentation.config import Dictation
from odsod_daemon.components.segmentation.vad import FRAME, Vad


def presence(pcm: bytes, settings: Dictation) -> tuple[bool, float]:
    vad = Vad()
    probabilities = [
        (vad.probability(pcm[i : i + FRAME * 2]), min(FRAME * 2, len(pcm) - i) / 32)
        for i in range(0, len(pcm), FRAME * 2)
    ]
    duration = sum(
        ms
        for probability, ms in probabilities
        if probability >= settings.presence_threshold
    )
    return duration >= settings.presence_min_ms, max(
        (p for p, _ in probabilities), default=0
    )
