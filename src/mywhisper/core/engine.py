from __future__ import annotations

import gc
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from mywhisper.core.types import (
    AudioSource,
    DeviceConfig,
    ModelSpec,
    Segment,
    TranscribeOptions,
    TranscriptionInfo,
)
from mywhisper.gpu.rocm_env import CPU

log = logging.getLogger(__name__)


class ModelNotAvailableError(RuntimeError):
    pass


class TranscriptionEngine(Protocol):
    """What the UI relies on. Other backends (whisper.cpp, transformers...) plug in here."""

    @property
    def device(self) -> DeviceConfig: ...

    @property
    def model(self) -> ModelSpec | None: ...

    def load(self, spec: ModelSpec) -> None: ...

    def unload(self) -> None: ...

    def transcribe(
        self, audio: AudioSource, options: TranscribeOptions
    ) -> tuple[TranscriptionInfo, Iterator[Segment]]: ...


class FasterWhisperEngine:
    def __init__(
        self,
        device: DeviceConfig,
        models_dir: Path,
        allow_download: bool = True,
        cpu_fallback: bool = True,
    ) -> None:
        self._device = device
        self._models_dir = models_dir
        self._allow_download = allow_download
        self._cpu_fallback = cpu_fallback
        self._spec: ModelSpec | None = None
        self._model = None

    @property
    def device(self) -> DeviceConfig:
        return self._device

    @property
    def model(self) -> ModelSpec | None:
        return self._spec

    def load(self, spec: ModelSpec) -> None:
        if self._spec == spec and self._model is not None:
            return
        self.unload()
        path = self._resolve(spec)

        from faster_whisper import WhisperModel

        try:
            self._model = WhisperModel(
                path, device=self._device.device, compute_type=self._device.compute_type
            )
        except Exception:
            if not (self._device.is_gpu and self._cpu_fallback):
                raise
            log.exception("Loading %s on GPU failed, retrying on CPU", spec.model_name)
            self._device = CPU
            self._model = WhisperModel(path, device=CPU.device, compute_type=CPU.compute_type)
        self._spec = spec

    def unload(self) -> None:
        self._model = None
        self._spec = None
        gc.collect()

    def transcribe(
        self, audio: AudioSource, options: TranscribeOptions
    ) -> tuple[TranscriptionInfo, Iterator[Segment]]:
        if self._model is None or self._spec is None:
            raise RuntimeError("Aucun modèle chargé")
        if isinstance(audio, Path):
            audio = str(audio)
        segments, info = self._model.transcribe(
            audio,
            language=options.language,
            beam_size=self._spec.beam_size,
            condition_on_previous_text=self._spec.condition_on_previous_text,
            vad_filter=options.vad_filter,
            vad_parameters={"min_silence_duration_ms": 500} if options.vad_filter else None,
        )
        result = TranscriptionInfo(info.language, info.language_probability, info.duration)
        return result, (Segment(s.start, s.end, s.text.strip()) for s in segments)

    def _resolve(self, spec: ModelSpec) -> str:
        """Local cache first (works offline), then download if allowed."""
        from faster_whisper.utils import download_model

        try:
            return download_model(
                spec.model_name, cache_dir=str(self._models_dir), local_files_only=True
            )
        except Exception:
            if not self._allow_download:
                raise ModelNotAvailableError(
                    f"Modèle {spec.model_name} absent de {self._models_dir}. "
                    "Lancez scripts/download_models.py une fois avec une connexion."
                ) from None
        log.info("Downloading %s to %s", spec.model_name, self._models_dir)
        return download_model(spec.model_name, cache_dir=str(self._models_dir))
