"""Plain data shared by every layer: audio, segments, words, options, device.

All frozen dataclasses: a Segment handed to the UI, the history or an exporter
can never be modified behind their back; edits create new instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np

# A file path (decoded by PyAV inside faster-whisper) or 16 kHz mono float32 samples.
AudioSource = str | Path | np.ndarray

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str  # as produced by Whisper, usually with a leading space
    probability: float | None = None  # confidence, 0 to 1 (files only)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    words: tuple[Word, ...] = ()  # filled when word timestamps are requested


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    model_name: str
    beam_size: int
    condition_on_previous_text: bool
    size_gb: float = 0.0  # download size, shown before downloading
    description: str = ""


@dataclass(frozen=True)
class TranscribeOptions:
    language: str | None = None  # None = auto-detect
    vad_filter: bool = True
    initial_prompt: str | None = None  # preceding text, for context across live windows
    word_timestamps: bool = False
    hotwords: str | None = None  # user vocabulary, favoured by the decoder
    task: str = "transcribe"  # or "translate" (to English)
    multilingual: bool = False  # language may change within the audio
    beam_size: int = 0  # 0 = the model's default
    condition_on_previous_text: bool | None = None  # None = the model's default
    vad_threshold: float = 0.5  # speech probability above which audio counts as speech
    vad_min_silence_ms: int = 500  # shorter pauses do not split the audio
    hallucination_silence_s: float | None = None  # skip text invented in long silences
    no_speech_threshold: float = 0.6
    repetition_penalty: float = 1.0
    batch_size: int = 0  # > 1: batched inference (files, needs the VAD)


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
