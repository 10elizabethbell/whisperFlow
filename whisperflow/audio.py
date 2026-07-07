"""Microphone capture with energy-based VAD.

The stream is opened on demand (when recording starts) and closed after
each utterance, so the mic is idle between recordings.

While recording, each ~32ms block's RMS is compared against a threshold
calibrated from the ambient noise at start(). The app uses this to
auto-stop when the speaker goes quiet. Counters are block-based (not
wall-clock) so the logic is deterministic and testable.
"""

from __future__ import annotations

import collections
import math
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000  # what Parakeet expects
CHANNELS = 1
BLOCK_SIZE = 512  # ~32ms per callback
BLOCK_SECONDS = BLOCK_SIZE / SAMPLE_RATE
PRE_ROLL_SECONDS = 0.5

# VAD tuning
NOISE_FLOOR_MULT = 3.5  # speech threshold = noise floor * this ...
MIN_SPEECH_RMS = 0.01  # ... but never below this absolute RMS
SPEECH_ONSET_BLOCKS = 3  # ~100ms of consecutive loud blocks counts as speech


class Recorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recording = False
        self._chunks: list[np.ndarray] = []
        pre_roll_blocks = int(PRE_ROLL_SECONDS * SAMPLE_RATE / BLOCK_SIZE) + 1
        self._pre_roll: collections.deque[np.ndarray] = collections.deque(
            maxlen=pre_roll_blocks
        )
        self._threshold = MIN_SPEECH_RMS
        self._speech_run = 0
        self._silence_blocks = 0
        self._recorded_blocks = 0
        self._has_speech = False
        self._stream: sd.InputStream | None = None

    def _callback(self, indata: np.ndarray, frames, time, status) -> None:
        if status:
            print(f"[audio] {status}", flush=True)
        mono = indata[:, 0].copy()
        with self._lock:
            if self._recording:
                self._chunks.append(mono)
                self._recorded_blocks += 1
                self._track_speech(mono)
            else:
                self._pre_roll.append(mono)

    def _track_speech(self, block: np.ndarray) -> None:
        rms = math.sqrt(float(np.mean(block**2)))
        if rms >= self._threshold:
            self._speech_run += 1
            self._silence_blocks = 0
            if self._speech_run >= SPEECH_ONSET_BLOCKS:
                self._has_speech = True
        else:
            self._speech_run = 0
            self._silence_blocks += 1

    def open(self) -> None:
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=BLOCK_SIZE,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def start(self) -> None:
        with self._lock:
            pre_roll = list(self._pre_roll)
            self._chunks = pre_roll
            self._pre_roll.clear()
            self._recording = True
            self._speech_run = 0
            self._silence_blocks = 0
            self._recorded_blocks = 0
            self._has_speech = False
            self._threshold = _calibrate_threshold(pre_roll)

    def stop(self) -> np.ndarray:
        """Stop capturing and return the utterance as float32 samples."""
        with self._lock:
            self._recording = False
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    # --- state for the auto-stop logic (menubar timer polls these) ---

    @property
    def has_speech(self) -> bool:
        with self._lock:
            return self._has_speech

    @property
    def silence_seconds(self) -> float:
        with self._lock:
            return self._silence_blocks * BLOCK_SECONDS

    @property
    def recorded_seconds(self) -> float:
        with self._lock:
            return self._recorded_blocks * BLOCK_SECONDS


def _calibrate_threshold(pre_roll: list[np.ndarray]) -> float:
    """Speech threshold from the ambient noise in the pre-roll buffer."""
    if not pre_roll:
        return MIN_SPEECH_RMS
    rms_values = sorted(math.sqrt(float(np.mean(b**2))) for b in pre_roll)
    noise_floor = rms_values[len(rms_values) // 2]  # median
    return max(noise_floor * NOISE_FLOOR_MULT, MIN_SPEECH_RMS)
