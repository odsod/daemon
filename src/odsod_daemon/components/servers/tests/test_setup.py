"""ADR-0023: setup adopts, downloads, unpacks and builds, all once."""

import hashlib
import io
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from odsod_daemon.components.servers import pins, setup
from odsod_daemon.lib.download import Pin

pytestmark = pytest.mark.looptime(False)

BIN = Path(__file__).parent / "bin"


def tarball(top: str, extra: str | None = None) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name in filter(None, (f"{top}/CMakeLists.txt", extra)):
            data = b"project(fake)\n"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def pin(url: str, name: str, data: bytes) -> Pin:
    return Pin(name, f"{url}/{name}", hashlib.sha256(data).hexdigest(), len(data))


class Host:
    def __init__(self, root: Path, server, legacy: Path):
        self.root = root
        self.state = root / "state"
        self.server = server
        self.legacy = legacy
        self.builds: dict[str, pins.Build] = {}
        self.models: dict[str, Pin] = {}
        for name, real in pins.BUILDS.items():
            data = tarball(real.directory)
            server.files[real.source.name] = data
            self.builds[name] = replace(
                real, source=pin(server.url, real.source.name, data)
            )
            model = f"{name} weights".encode()
            server.files[pins.MODELS[name].name] = model
            self.models[name] = pin(server.url, pins.MODELS[name].name, model)

    def run(self, **kwargs) -> list[str]:
        lines: list[str] = []
        kwargs.setdefault("progress", lines.append)
        return setup.run(
            builds=self.builds, models=self.models, legacy=self.legacy, **kwargs
        )

    def cmake(self) -> list[str]:
        log = self.root / "cmake.log"
        return log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def host(temp_root, tmp_path, monkeypatch, file_server):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home/.local/share"))
    monkeypatch.setenv("PATH", f"{BIN}:/usr/bin:/bin")
    return Host(
        temp_root, file_server, tmp_path / "home/.local/share/odsod/machine/data"
    )


def test_fresh_host_downloads_and_builds_once(host):
    changes = host.run()
    assert changes == [
        "whisper: downloaded ggml-large-v3.bin",
        "whisper: downloaded whisper.cpp-1.9.5",
        "whisper: built whisper-server 1.9.5",
        "llama: downloaded Qwen3.5-9B-Q5_K_M.gguf",
        "llama: downloaded llama.cpp-1.0.0-b12359-b1b770d",
        "llama: built llama-server 1.0.0-b12359-b1b770d",
    ]
    for name, build in pins.BUILDS.items():
        assert (host.state / build.binary).read_text() == f"fake {build.target}\n"
        assert (host.state / "models" / pins.MODELS[name].name).exists()
        # The tarball goes once its tree is in place.
        assert not (host.state / "servers" / build.source.name).exists()
    log = host.cmake()
    assert (
        "whisper.cpp-1.9.5: cmake -B build -DWHISPER_BUILD_SERVER=ON -DGGML_HIP=ON "
        "-DCMAKE_HIP_ARCHITECTURES=gfx1200 -DGGML_NATIVE=ON "
        "-DCMAKE_BUILD_TYPE=Release" in log
    )
    assert any(
        line.startswith(
            "llama.cpp-1.0.0-b12359-b1b770d: cmake --build build --target llama-server"
        )
        for line in log
    )
    assert any("-DLLAMA_BUILD_NUMBER=12359" in line for line in log)
    gets = len(host.server.gets)
    assert host.run() == []
    assert len(host.server.gets) == gets
    assert host.cmake() == log


def test_adopts_matching_models_and_downloads_the_rest(host):
    whisper = host.legacy / "whisper" / host.models["whisper"].name
    whisper.parent.mkdir(parents=True)
    whisper.write_bytes(host.server.files[host.models["whisper"].name])
    # Same size, other bytes: the hash check refuses it.
    llama = host.legacy / "llama" / host.models["llama"].name
    llama.parent.mkdir(parents=True)
    llama.write_bytes(b"x" * host.models["llama"].size)
    changes = host.run()
    assert f"whisper: adopted ggml-large-v3.bin from {whisper.parent}" in changes
    assert "llama: downloaded Qwen3.5-9B-Q5_K_M.gguf" in changes
    assert host.models["whisper"].name not in host.server.gets
    assert not whisper.exists()
    assert llama.exists()


def test_check_changes_nothing(host):
    lines: list[str] = []
    assert host.run(check=True, progress=lines.append) == []
    assert lines == [
        "whisper: model missing, binary missing; "
        "to do: download-model, download-source, build",
        "llama: model missing, binary missing; "
        "to do: download-model, download-source, build",
    ]
    assert host.server.gets == []
    assert not (host.state / "servers").exists()
    assert not (host.state / "models").exists()


def test_missing_tools_stop_before_any_change(host, monkeypatch, tmp_path):
    only = tmp_path / "only-cmake"
    only.mkdir()
    (only / "cmake").symlink_to(BIN / "cmake")
    monkeypatch.setenv("PATH", str(only))
    with pytest.raises(setup.SetupError) as error:
        host.run()
    message = str(error.value)
    assert "hipcc, g++" in message
    assert "hipblas-devel" in message and "machine repo" in message
    assert host.server.gets == []


def test_bad_tarball_hash_leaves_no_tree(host):
    whisper = host.builds["whisper"]
    host.builds["whisper"] = replace(
        whisper, source=replace(whisper.source, sha256="0" * 64)
    )
    with pytest.raises(setup.SetupError, match="SHA-256"):
        host.run()
    assert not (host.state / "servers" / whisper.directory).exists()
    assert not list((host.state / "servers").glob("*.part"))


def test_failed_build_reruns_the_build_only(host, monkeypatch):
    monkeypatch.setenv("FAKE_CMAKE_FAIL", "llama-server")
    with pytest.raises(setup.SetupError, match="llama-server"):
        host.run()
    monkeypatch.delenv("FAKE_CMAKE_FAIL")
    gets = len(host.server.gets)
    assert host.run() == ["llama: built llama-server 1.0.0-b12359-b1b770d"]
    assert len(host.server.gets) == gets


def test_cli_check_reads_the_real_pins(host):
    from odsod_daemon.cli import app

    result = CliRunner().invoke(app, ["inference", "setup", "--check"])
    assert result.exit_code == 0, result.output
    assert "whisper: model missing" in result.output
    assert host.server.gets == []
    assert not (host.state / "models").exists()
