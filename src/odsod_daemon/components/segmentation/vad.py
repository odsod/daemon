"""Silero v5.1.2, CPU only, with private recurrent state per instance."""

from pathlib import Path
from typing import cast

import numpy as np
import onnxruntime as ort
from numpy.typing import NDArray

MODEL_TAG = "v5.1.2"
MODEL_SHA256 = "2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f"
MODEL = Path(__file__).parent / "models" / "silero_vad.onnx"
FRAME = 512


class Vad:
    def __init__(self, energy_floor_dbfs: float = -65):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(MODEL), options, providers=["CPUExecutionProvider"]
        )
        self.energy_floor_dbfs = energy_floor_dbfs
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def probability(self, pcm: bytes) -> float:
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        if len(samples) > FRAME:
            raise ValueError("VAD takes at most 512 samples")
        rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0
        if rms == 0 or 20 * np.log10(rms / 32768) < self.energy_floor_dbfs:
            self.reset()
            return 0.0
        samples = np.pad(samples / 32768, (0, FRAME - len(samples)))
        inputs = np.concatenate((self.context, samples.reshape(1, FRAME)), axis=1)
        outputs = self.session.run(
            None,
            {
                "input": inputs,
                "state": self.state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        probability = cast(NDArray[np.float32], outputs[0])
        self.state = cast(NDArray[np.float32], outputs[1])
        self.context = inputs[:, -64:].copy()
        return float(probability[0, 0])
