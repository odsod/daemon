"""Summary validation and line-based chunks."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

LABELS = ("Decided", "Insight", "Problem", "Context", "Next")


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: Literal["Decided", "Insight", "Problem", "Context", "Next"]
    text: str
    owner: str | None


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    skip: bool
    title: str
    overview: str
    points: list[Point]


def validate(reply: str, title_max_words: int = 8) -> Summary:
    value = json.loads(re.sub(r"<think>.*?</think>", "", reply, flags=re.S))
    value["points"] = [
        p
        for p in value["points"]
        if p.get("label") in LABELS and p.get("text", "").strip()
    ]
    summary = Summary.model_validate(value)
    summary.title = " ".join(summary.title.split()[:title_max_words])
    summary.overview = " ".join(re.split(r"(?<=[.!?])\s+", summary.overview)[:3])
    return summary


def chunks(text: str, limit: int) -> list[str]:
    result: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            raise ValueError("one transcript line exceeds chunk_chars")
        if current and len(current) + len(line) > limit:
            result.append(current)
            current = ""
        current += line
    if current:
        result.append(current)
    return result


class Summarizer:
    """Render prompts once per pass and summarize through one llama slot."""

    def __init__(self, config, roots, url: str):
        import hashlib
        from pathlib import Path

        from jinja2 import Environment, StrictUndefined

        from odsod_daemon.lib import inference

        self.config = config
        self.client = inference.LlamaClient(
            url, model=config.model, timeout_s=config.request_timeout_s
        )
        shipped = Path(__file__).parent / "prompts"
        glossary_path = roots.config / "glossary.txt"
        glossary = (
            glossary_path.read_text().splitlines() if glossary_path.exists() else []
        )
        self.prompts = {}
        for name in ("summarize", "combine"):
            override = roots.config / "prompts" / f"interactions-{name}.md"
            source = override if override.exists() else shipped / f"{name}.md"
            self.prompts[name] = (
                Environment(undefined=StrictUndefined, autoescape=False)
                .from_string(source.read_text())
                .render(
                    owner_name=config.owner_name,
                    languages=config.languages,
                    glossary=glossary,
                    title_max_words=config.title_max_words,
                )
                .strip()
            )
        self.schema = json.loads((shipped / "summary.schema.json").read_text())
        digest = hashlib.sha256(
            json.dumps(self.prompts, sort_keys=True).encode()
        ).hexdigest()
        self.setup = f"{config.model}:{digest}"

    async def request(self, name: str, text: str) -> Summary:
        reply = await self.client.complete(
            [
                {"role": "system", "content": self.prompts[name]},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "summary", "schema": self.schema},
            },
        )
        return validate(reply, self.config.title_max_words)

    async def __call__(self, text: str) -> tuple[Summary, str]:
        parts = chunks(text, self.config.chunk_chars)
        summaries = [await self.request("summarize", part) for part in parts]
        if len(summaries) == 1:
            return summaries[0], self.setup
        combined = await self.request(
            "combine", "\n".join(s.model_dump_json() for s in summaries)
        )
        return combined, self.setup
