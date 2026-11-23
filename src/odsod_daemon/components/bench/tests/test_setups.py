import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from odsod_daemon.components.bench import setups
from odsod_daemon.components.bench.tests.conftest import config

SETUP = {
    "name": "large",
    "kind": "pipeline",
    "asr": {"model": "ggml-large-v3-turbo", "revision": "2024-10"},
    "cleanup": {"model": "qwen3", "revision": "q4_k_m"},
}


def write_setup(root: Path, **overrides) -> setups.Setup:
    value = json.loads(json.dumps(SETUP))
    value.update(overrides)
    return setups.Setup.model_validate(value)


def test_fingerprint_ignores_name_and_covers_the_rest(bench_root):
    first = setups.manifest(write_setup(bench_root), setups.paths.roots())
    renamed = setups.manifest(
        write_setup(bench_root, name="other"), setups.paths.roots()
    )
    assert first.fingerprint == renamed.fingerprint
    assert first.name == "large" and renamed.name == "other"


@pytest.mark.parametrize(
    "change",
    [
        {"asr": {"model": "ggml-large-v3", "revision": "2024-10"}},
        {"cleanup": {"model": "qwen3", "revision": "q8_0"}},
        {"kind": "asr", "cleanup": None},
        {"asr": {"model": "ggml-large-v3-turbo", "settings": {"attempts": 1}}},
        {"cleanup": {"model": "qwen3", "ambient_prompt": "terse"}},
    ],
)
def test_fingerprint_changes_with_the_setup(bench_root, change):
    base = setups.manifest(write_setup(bench_root), setups.paths.roots())
    changed = setups.manifest(write_setup(bench_root, **change), setups.paths.roots())
    assert base.fingerprint != changed.fingerprint


def test_fingerprint_changes_with_glossary_prompt_and_commit(bench_root):
    roots = setups.paths.roots()
    base = setups.manifest(write_setup(bench_root), roots).fingerprint
    (bench_root / "config/glossary.txt").write_text("Ångström\n")
    assert setups.manifest(write_setup(bench_root), roots).fingerprint != base

    base = setups.manifest(write_setup(bench_root), roots).fingerprint
    (bench_root / "config/prompts").mkdir(parents=True, exist_ok=True)
    (bench_root / "config/prompts/cleanup.md").write_text("New prompt\n")
    assert setups.manifest(write_setup(bench_root), roots).fingerprint != base

    base = setups.manifest(write_setup(bench_root), roots).fingerprint
    (bench_root / "state/install").mkdir(parents=True, exist_ok=True)
    (bench_root / "state/install/current").write_text(
        json.dumps({"source": "dev", "commit": "abc", "installed_at": "now"})
    )
    assert setups.manifest(write_setup(bench_root), roots).fingerprint != base


def test_settings_merge_overrides_the_host_section(bench_root):
    config(bench_root, speech={"ambient": {"language": "auto", "languages": ["sv"]}})
    setup = write_setup(
        bench_root,
        asr={
            "model": "m",
            "settings": {"ambient": {"languages": ["sv", "en"]}, "attempts": 1},
        },
    )
    settings = setups.speech_settings(setup, setups.paths.roots())
    assert settings["ambient"] == {"language": "auto", "languages": ["sv", "en"]}
    assert settings["attempts"] == 1

    manifest = setups.manifest(setup, setups.paths.roots())
    assert manifest.settings == settings
    assert manifest.prompt_sha256


def test_public_url_is_refused():
    with pytest.raises(ValidationError, match="localhost or the tailnet"):
        setups.Setup.model_validate(
            {
                "name": "cloud",
                "kind": "asr",
                "asr": {"model": "m", "whisper_url": "https://api.example.com/v1"},
            }
        )
    assert setups.Setup.model_validate(
        {
            "name": "tailnet",
            "kind": "asr",
            "asr": {"model": "m", "whisper_url": "http://100.64.0.2/v1/audio"},
        }
    )


def test_live_fingerprint_names_both_setups():
    assert setups.live_fingerprint("a", "b") == "live-a-b"
    assert setups.live_fingerprint(None, None) == "live-none-none"
