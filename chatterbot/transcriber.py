"""Parakeet (MLX) transcription wrapper.

Loads nvidia/parakeet-tdt-0.6b-v3 converted for MLX (~1.2GB, downloaded
from HuggingFace on first run) and keeps it in memory so each utterance
transcribes in ~0.5s on Apple Silicon.

Feeds samples straight into the model (get_logmel + generate) instead of
model.transcribe(path), which shells out to ffmpeg.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
SAMPLE_RATE = 16_000


class Transcriber:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from parakeet_mlx import from_pretrained

        print(f"[model] loading {model_name} ...", flush=True)
        t0 = time.perf_counter()
        self._model = from_pretrained(model_name)
        print(f"[model] loaded in {time.perf_counter() - t0:.1f}s", flush=True)

    def warm_up(self) -> None:
        """Run a dummy transcription so the first real one isn't slow."""
        silence = np.zeros(SAMPLE_RATE // 2, dtype=np.float32)
        self.transcribe(silence)

    def transcribe(self, samples: np.ndarray) -> str:
        """Transcribe float32 mono samples at 16kHz."""
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel

        if samples.size == 0:
            return ""
        # must be float32: get_logmel bit-views the rfft output against the
        # input dtype, which breaks for anything else (load_audio also
        # returns float32)
        audio = mx.array(samples).astype(mx.float32)
        mel = get_logmel(audio, self._model.preprocessor_config)
        result = self._model.generate(mel)[0]
        return result.text.strip()

    def transcribe_file(self, path: str) -> str:
        """Transcribe a 16kHz mono 16-bit wav (test helper, stdlib decode only)."""
        with wave.open(str(Path(path)), "rb") as wf:
            if wf.getframerate() != SAMPLE_RATE or wf.getnchannels() != 1:
                raise ValueError(
                    f"expected {SAMPLE_RATE}Hz mono wav; convert with: "
                    f"afconvert -f WAVE -d LEI16@16000 -c 1 IN {path}"
                )
            pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return self.transcribe(pcm.astype(np.float32) / 32768.0)
