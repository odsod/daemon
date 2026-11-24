"""The pinned server sources, build flags and models.

A version bump is a pull request that edits this file.
"""

from __future__ import annotations

from dataclasses import dataclass

from odsod_daemon.lib.download import Pin

# The Radeon RX 9060 XT of the inference host.
HIP = (
    "-DGGML_HIP=ON",
    "-DCMAKE_HIP_ARCHITECTURES=gfx1200",
    "-DGGML_NATIVE=ON",
    "-DCMAKE_BUILD_TYPE=Release",
)
TOOLS = ("cmake", "hipcc", "g++")
# The OS packages that give TOOLS and the ROCm libraries. The machine repo
# installs them on the inference host.
PACKAGES = (
    "cmake",
    "gcc-c++",
    "hipblas-devel",
    "hipcc",
    "rocblas-devel",
    "rocm-hip",
)


@dataclass(frozen=True)
class Build:
    server: str
    project: str
    version: str
    source: Pin
    target: str
    cmake: tuple[str, ...]

    @property
    def directory(self) -> str:
        """The source tree in state/servers/; the tarball's top folder."""
        return f"{self.project}-{self.version}"

    @property
    def binary(self) -> str:
        """The built server, relative to the state root."""
        return f"servers/{self.directory}/build/bin/{self.target}"


WHISPER_VERSION = "1.9.5"
LLAMA_VERSION = "1.0.0-b12359-b1b770d"

BUILDS: dict[str, Build] = {
    "whisper": Build(
        server="whisper",
        project="whisper.cpp",
        version=WHISPER_VERSION,
        source=Pin(
            f"whisper.cpp-{WHISPER_VERSION}.tar.gz",
            "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/"
            f"v{WHISPER_VERSION}.tar.gz",
            "ff1a9053feb509ff9d7729703355541ae9690073a6b1c40eb692c962e0dc1720",
            9626464,
        ),
        target="whisper-server",
        cmake=("-DWHISPER_BUILD_SERVER=ON", *HIP),
    ),
    "llama": Build(
        server="llama",
        project="llama.cpp",
        version=LLAMA_VERSION,
        source=Pin(
            f"llama.cpp-{LLAMA_VERSION}.tar.gz",
            "https://github.com/ggml-org/llama.cpp/archive/refs/tags/"
            f"v{LLAMA_VERSION}.tar.gz",
            "79465cbc4d52f8d95ac61948a6ca8275517dc7e7eda6e702f162b3fd2a1605d7",
            38899849,
        ),
        target="llama-server",
        # A tarball has no Git history. Without the tag's build number,
        # llama.cpp asks for web UI assets of build 0, which do not exist.
        cmake=(*HIP, "-DLLAMA_BUILD_NUMBER=12359"),
    ),
}

MODELS: dict[str, Pin] = {
    "whisper": Pin(
        "ggml-large-v3.bin",
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/"
        "5359861c739e955e79d9a303bcbc70fb988958b1/ggml-large-v3.bin",
        "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
        3095033483,
    ),
    "llama": Pin(
        "Qwen3.5-9B-Q5_K_M.gguf",
        "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/"
        "3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q5_K_M.gguf",
        "dc2a39aef291f91a9116ad214058da0d86eb648743a124bd8c333787c4b9c91c",
        6577841376,
    ),
}

# Where the machine repo kept the models, below $XDG_DATA_HOME. Setup moves a
# file that matches its pin, so the host never downloads it twice.
LEGACY = "odsod/machine/data"
