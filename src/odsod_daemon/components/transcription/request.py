"""Build Whisper fields and an in-memory WAV without I/O."""

import io
import wave

from odsod_daemon.components.segmentation.config import Speech


def glossary_tail(glossary: list[str], limit: int) -> str:
    selected: list[str] = []
    for term in reversed(glossary):
        if len(", ".join([term, *selected])) > limit:
            break
        selected.insert(0, term)
    return ", ".join(selected)


def fields(dictation: bool, speech: Speech, glossary: list[str]) -> dict[str, str]:
    result = {
        "language": "en" if dictation else speech.ambient.language,
        "prompt": glossary_tail(glossary, speech.glossary_prompt_chars),
        "response_format": "verbose_json",
        "temperature": "0",
    }
    if dictation:
        result.update(
            entropy_thold=str(speech.dictation.entropy_thold),
            logprob_thold=str(speech.dictation.logprob_thold),
        )
    return result


def wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(pcm)
    return output.getvalue()
