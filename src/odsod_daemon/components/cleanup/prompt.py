"""Render shipped cleanup templates or owner overrides."""

from pathlib import Path

from jinja2 import Environment, StrictUndefined

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


def messages(system: str, text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"<transcript>{text}</transcript>"},
    ]
