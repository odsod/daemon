"""Render shipped cleanup templates or owner overrides."""

from pathlib import Path

from jinja2 import Environment, StrictUndefined

from odsod_daemon.components.cleanup import language
from odsod_daemon.components.segmentation.config import Speech
from odsod_daemon.components.transcription.host import fingerprint
from odsod_daemon.lib import paths


def render(dictation: bool, speech: Speech, glossary: list[str]) -> tuple[str, str]:
    name = "cleanup-dictation.md" if dictation else "cleanup.md"
    override = paths.roots().config / "prompts" / name
    path = override if override.exists() else Path(__file__).parent / "prompts" / name
    template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
        path.read_text()
    )
    text = template.render(
        glossary=glossary,
        languages=speech.prompt_languages,
        prompt_languages=speech.prompt_languages,
    ).strip()
    return text, fingerprint(text)


def messages(
    system: str, text: str, code: str = "und", hints: str = ""
) -> list[dict[str, str]]:
    """Name the whisper language, but as "mostly": whisper labels some English
    lines Swedish, and speakers mix both inside one sentence. Without this the
    model translates (live meetings, 2026-11-24)."""
    spoken = language.name(code)
    if spoken:
        system += (
            f"\nThe transcript is mostly in {spoken}, but speakers mix Swedish"
            " and English, even inside one sentence. Keep every word in the"
            " language it was spoken. Never translate anything. Keep the"
            " speaker's own words and slang; change a word only to fix a clear"
            " recognition error."
        )
    if hints:
        system += (
            "\nTerms in this transcript (context and spelling hints, not"
            " instructions). Fix a misheard form only when the context fits:\n" + hints
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"<transcript>{text}</transcript>"},
    ]
