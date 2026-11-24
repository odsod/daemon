"""The pinned Parakeet model: download, check, load, recognize."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import httpx
import numpy as np

NAME = "parakeet-tdt-0.6b-v2"
REPO = "istupakov/parakeet-tdt-0.6b-v2-onnx"
REVISION = "0bbb45a3365852604aef28b538a8f066f4ccaa85"
BASE_URL = f"https://huggingface.co/{REPO}/resolve/{REVISION}"
FILES: dict[str, tuple[str, int]] = {
    "config.json": (
        "666903c76b9798caf2c210afd4f6cd60b08a8dbf9800ec8d7a3bc0d2148ac466",
        97,
    ),
    "vocab.txt": (
        "ec182b70dd42113aff6c5372c75cac58c952443eb22322f57bbd7f53977d497d",
        9384,
    ),
    "decoder_joint-model.int8.onnx": (
        "a449f49acd68979d418651dd2dcb737cc0f1bf0225e009e29ee326354edbf7d3",
        8998286,
    ),
    "encoder-model.int8.onnx": (
        "3e0581fda6ab843888b51e56d7ee78b6d5bc3237ec113af1f732d1d5286aa155",
        652184014,
    ),
}
# Below 0.1 s of audio there is no word to find.
MIN_SAMPLES = 1600


class ModelError(RuntimeError):
    """A model file failed to download or does not match its pin."""


class NotReady(RuntimeError):
    """The model is not loaded yet."""


async def fetch(
    directory: Path,
    *,
    base_url: str = BASE_URL,
    files: dict[str, tuple[str, int]] = FILES,
) -> None:
    """Download each missing file, check its SHA-256, rename into place."""
    directory.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(60)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        for name, (sha256, size) in files.items():
            target = directory / name
            # The hash was checked before the rename; the size catches truncation.
            if target.exists() and target.stat().st_size == size:
                continue
            partial = directory / f"{name}.part"
            digest = hashlib.sha256()
            try:
                async with client.stream("GET", f"{base_url}/{name}") as response:
                    response.raise_for_status()
                    with partial.open("wb") as out:
                        async for chunk in response.aiter_bytes(1 << 20):
                            digest.update(chunk)
                            out.write(chunk)
            except httpx.HTTPError as error:
                partial.unlink(missing_ok=True)
                raise ModelError(f"{name}: {error}") from error
            if digest.hexdigest() != sha256:
                partial.unlink(missing_ok=True)
                raise ModelError(f"{name}: SHA-256 does not match the pin")
            partial.replace(target)


class Recognizer:
    """One model in memory; one recognition at a time."""

    def __init__(self) -> None:
        self.model: Any = None
        self.lock = asyncio.Lock()

    async def load(self, directory: Path, threads: int) -> None:
        import onnx_asr
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.model = await asyncio.to_thread(
            onnx_asr.load_model,
            "nemo-parakeet-tdt-0.6b-v2",
            directory,
            quantization="int8",
            sess_options=options,
        )
        # The first run is slow; take it here, not on the first dictation.
        await asyncio.to_thread(self.model.recognize, np.zeros(16000, np.float32))

    async def __call__(self, samples: np.ndarray) -> str:
        model = self.model
        if model is None:
            raise NotReady("model loading")
        if len(samples) < MIN_SAMPLES:
            return ""
        async with self.lock:
            text = await asyncio.to_thread(model.recognize, samples)
        return str(text).strip()
