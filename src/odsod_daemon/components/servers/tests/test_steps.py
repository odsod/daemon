import pytest

from odsod_daemon.components.servers import contract, pins
from odsod_daemon.components.servers.steps import Found, describe, missing_tools, steps


@pytest.mark.parametrize(
    "model,legacy,source,binary,expected",
    [
        (True, False, True, True, ()),
        (True, True, True, True, ()),
        (False, True, True, True, ("adopt",)),
        (False, False, True, True, ("download-model",)),
        (True, False, True, False, ("build",)),
        (True, False, False, False, ("download-source", "build")),
        # A binary without its source tree is still ready.
        (True, False, False, True, ()),
        (False, False, False, False, ("download-model", "download-source", "build")),
        (False, True, False, False, ("adopt", "download-source", "build")),
    ],
)
def test_steps(model, legacy, source, binary, expected):
    assert steps(Found(model, legacy, source, binary)) == expected


@pytest.mark.parametrize(
    "found,line",
    [
        (Found(True, False, True, True), "whisper: model present, binary built; ready"),
        (
            Found(False, True, True, False),
            "whisper: model missing, binary missing; to do: adopt, build",
        ),
    ],
)
def test_describe(found, line):
    assert describe("whisper", found) == line


@pytest.mark.parametrize(
    "found,missing",
    [
        ({"cmake", "hipcc", "g++"}, []),
        ({"cmake"}, ["hipcc", "g++"]),
        (set(), ["cmake", "hipcc", "g++"]),
    ],
)
def test_missing_tools(found, missing):
    assert missing_tools(pins.TOOLS, found) == missing


def test_pins_are_fixed():
    for name, build in pins.BUILDS.items():
        assert build.server == name
        assert build.source.name == f"{build.directory}.tar.gz"
        assert f"v{build.version}.tar.gz" in build.source.url
        assert "-DCMAKE_HIP_ARCHITECTURES=gfx1200" in build.cmake
        assert len(build.source.sha256) == 64
    assert "-DLLAMA_BUILD_NUMBER=12359" in pins.BUILDS["llama"].cmake
    assert "-DWHISPER_BUILD_SERVER=ON" in pins.BUILDS["whisper"].cmake
    for model in pins.MODELS.values():
        # A fixed revision, never a branch.
        assert "/resolve/main/" not in model.url
        assert model.url.endswith(f"/{model.name}")
        assert len(model.sha256) == 64


def test_server_facts_match_the_pins():
    by_name = {server.name: server for server in contract.SERVERS}
    assert by_name["whisper"].binary == (
        "servers/whisper.cpp-1.9.5/build/bin/whisper-server"
    )
    assert by_name["llama"].model == "models/Qwen3.5-9B-Q5_K_M.gguf"
    llama = " ".join(by_name["llama"].args)
    assert "--parallel 4 --kv-unified" in llama
    assert "--spec-type ngram-simple" in llama
    assert "--inference-path /v1/audio/transcriptions" in " ".join(
        by_name["whisper"].args
    )


def test_config_defaults_and_partial_sections():
    assert contract.Inference().enabled is False
    section = contract.Inference.model_validate(
        {"enabled": True, "llama": {"extra_args": ["--verbose"]}}
    )
    assert (section.whisper.port, section.llama.port) == (8178, 8179)
    assert section.llama.extra_args == ["--verbose"]
    with pytest.raises(ValueError):
        contract.Inference.model_validate({"whisper": {"port": 0}})
    with pytest.raises(ValueError):
        contract.Inference.model_validate({"other": 1})
