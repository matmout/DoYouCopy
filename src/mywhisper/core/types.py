from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np

# A file path (decoded by PyAV inside faster-whisper) or 16 kHz mono float32 samples.
AudioSource = Union[str, Path, np.ndarray]

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    model_name: str
    beam_size: int
    condition_on_previous_text: bool


@dataclass(frozen=True)
class TranscribeOptions:
    language: str | None = None  # None = auto-detect
    vad_filter: bool = True


@dataclass(frozen=True)
class TranscriptionInfo:
    language: str
    language_probability: float
    duration: float


@dataclass(frozen=True)
class DeviceConfig:
    device: str  # "cuda" (HIP on AMD) or "cpu"
    compute_type: str
    description: str

    @property
    def is_gpu(self) -> bool:
        return self.device != "cpu"
