from __future__ import annotations

import gc
import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from mywhisper.core import model_download
from mywhisper.core.types import (
    AudioSource,
    DeviceConfig,
    ModelSpec,
    Segment,
    TranscribeOptions,
    TranscriptionInfo,
    Word,
)
from mywhisper.gpu.rocm_env import CPU

log = logging.getLogger(__name__)


class ModelNotAvailableError(RuntimeError):
    pass


def _rocm_build() -> bool:
    """The ROCm build of CTranslate2 sits next to the ROCm runtime packages."""
    try:
        import ctranslate2

        return (Path(ctranslate2.__file__).parent.parent / "_rocm_sdk_core").is_dir()
    except Exception:
        return False


# Destroying a multi-threaded CPU model of the ROCm build of CTranslate2 never returns
# (its thread pool teardown deadlocks; the CPU/CUDA build from PyPI is fine). Such models
# are kept alive for the life of the process and reused: key = (path, compute type, threads).
_kept_cpu_models: dict[tuple, object] = {}


def _keep_forever(model) -> None:
    import ctypes

    ctypes.pythonapi.Py_IncRef(ctypes.py_object(model))  # never freed, not even at exit


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
        self._batched = None
        self._cpu_threads = 0  # 0 = automatic
        self._model_path = ""
        # (model spec, done bytes, total bytes) while a missing model downloads
        self.on_download_progress: Callable[[ModelSpec, int, int], None] | None = None

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

        kept = self._kept_key(path)
        if kept in _kept_cpu_models:
            self._model = _kept_cpu_models[kept]
            self._spec = spec
            self._model_path = path
            return
        try:
            self._model = WhisperModel(
                path, device=self._device.device, compute_type=self._device.compute_type, **self._threads()
            )
        except Exception:
            if not (self._device.is_gpu and self._cpu_fallback):
                raise
            log.exception("Loading %s on GPU failed, retrying on CPU", spec.model_name)
            self._device = CPU
            self._model = WhisperModel(path, device=CPU.device, compute_type=CPU.compute_type, **self._threads())
        self._spec = spec
        self._model_path = path

    def unload(self) -> None:
        if self._model is not None and not self._device.is_gpu and _rocm_build():
            key = self._kept_key(self._model_path)
            if key not in _kept_cpu_models:
                _keep_forever(self._model)
                _kept_cpu_models[key] = self._model
                log.info("CPU model kept in memory (ROCm build of CTranslate2 cannot free it)")
        self._model = None
        self._batched = None
        self._spec = None
        gc.collect()

    def transcribe(
        self, audio: AudioSource, options: TranscribeOptions
    ) -> tuple[TranscriptionInfo, Iterator[Segment]]:
        if self._model is None or self._spec is None:
            raise RuntimeError("Aucun modèle chargé")
        if isinstance(audio, Path):
            audio = str(audio)
        kwargs = self.transcribe_kwargs(options)
        if options.batch_size > 1 and options.vad_filter:
            # Batched inference decodes several VAD chunks at once: much faster on a GPU.
            from faster_whisper import BatchedInferencePipeline

            if self._batched is None:
                self._batched = BatchedInferencePipeline(self._model)
            segments, info = self._batched.transcribe(audio, batch_size=options.batch_size, **kwargs)
        else:
            segments, info = self._model.transcribe(audio, **kwargs)
        result = TranscriptionInfo(info.language, info.language_probability, info.duration)
        return result, (
            Segment(
                s.start,
                s.end,
                s.text.strip(),
                tuple(Word(w.start, w.end, w.word) for w in s.words or ()),
            )
            for s in segments
        )

    def transcribe_kwargs(self, options: TranscribeOptions) -> dict:
        spec = self._spec
        condition = options.condition_on_previous_text
        kwargs = dict(
            language=options.language,
            task=options.task,
            beam_size=options.beam_size or spec.beam_size,
            condition_on_previous_text=spec.condition_on_previous_text if condition is None else condition,
            vad_filter=options.vad_filter,
            initial_prompt=options.initial_prompt,
            word_timestamps=options.word_timestamps,
            hotwords=options.hotwords,
            multilingual=options.multilingual,
            no_speech_threshold=options.no_speech_threshold,
            repetition_penalty=options.repetition_penalty,
            vad_parameters=(
                {"threshold": options.vad_threshold, "min_silence_duration_ms": options.vad_min_silence_ms}
                if options.vad_filter
                else None
            ),
        )
        if options.hallucination_silence_s and options.word_timestamps:
            kwargs["hallucination_silence_threshold"] = options.hallucination_silence_s
        return kwargs

    def configure(
        self,
        device: DeviceConfig | None = None,
        cpu_threads: int | None = None,
        models_dir: Path | None = None,
        allow_download: bool | None = None,
    ) -> None:
        """Changes take effect at the next load(): the current model is unloaded."""
        if device is not None:
            self._device = device
        if cpu_threads is not None:
            self._cpu_threads = cpu_threads
        if models_dir is not None:
            self._models_dir = models_dir
        if allow_download is not None:
            self._allow_download = allow_download
        self.unload()

    def _kept_key(self, path: str) -> tuple:
        return (path, self._device.compute_type, self._threads().get("cpu_threads"))

    def _threads(self) -> dict:
        """On the CPU, one thread per physical core (about half the logical ones) unless set."""
        if self._device.is_gpu:
            return {}
        if self._cpu_threads:
            return {"cpu_threads": self._cpu_threads}
        logical = os.cpu_count() or 4
        return {"cpu_threads": max(4, logical // 2) if logical >= 8 else logical}

    def _resolve(self, spec: ModelSpec) -> str:
        """Local copies first (works offline), then a download with progress if allowed."""
        from faster_whisper.utils import download_model

        try:  # Hugging Face cache, filled by scripts/download_models.py
            return download_model(
                spec.model_name, cache_dir=str(self._models_dir), local_files_only=True
            )
        except Exception:
            pass
        directory = model_download.local_dir(self._models_dir, spec.model_name)
        if model_download.is_complete(directory):
            return str(directory)
        if not self._allow_download:
            raise ModelNotAvailableError(
                f"Modèle {spec.model_name} absent de {self._models_dir}. "
                "Autorisez le téléchargement (\"allow_download\") ou copiez le modèle."
            )
        log.info("Downloading %s to %s", spec.model_name, directory)

        def progress(done: int, total: int) -> None:
            if self.on_download_progress is not None:
                self.on_download_progress(spec, done, total)

        return str(model_download.download(spec.model_name, self._models_dir, progress))
