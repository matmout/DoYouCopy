from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from mywhisper.core.engine import TranscriptionEngine
from mywhisper.core.live import LiveTranscriber
from mywhisper.core.models import get_model
from mywhisper.core.types import TranscribeOptions

log = logging.getLogger(__name__)


class ModelWorker(QObject):
    """Owns the engine on a dedicated thread: one GPU user, a UI that never freezes.

    Requests arrive through the queued request_* signals, so they run one after
    another in the order they were sent.
    """

    request_load = Signal(str)
    request_transcribe = Signal(object, object)  # AudioSource, TranscribeOptions
    request_live = Signal(object, object)  # source with drain(), TranscribeOptions
    request_dictate = Signal(object, object, int)  # audio, TranscribeOptions, job id

    model_loading = Signal(str)  # model label
    model_downloading = Signal(str, int, int)  # model name, done bytes, total bytes
    model_loaded = Signal(str, str)  # model key, device description
    transcription_started = Signal(object)  # TranscriptionInfo
    segment_ready = Signal(object)  # Segment
    transcription_finished = Signal(float, float, bool)  # elapsed s, audio s, cancelled
    live_update = Signal(object, float)  # LiveUpdate, pass duration in s
    live_finished = Signal()
    error = Signal(str)
    # universal dictation: the whole text at once, kept away from the main window
    dictation_finished = Signal(int, str, str)  # job id, text, language
    dictation_failed = Signal(int, str)  # job id, message

    LIVE_POLL_S = 0.05

    def __init__(
        self,
        engine: TranscriptionEngine,
        live_factory: Callable[..., LiveTranscriber] = LiveTranscriber,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._live_factory = live_factory
        self._cancel = threading.Event()
        self._live_stop = threading.Event()
        self._last_download_emit = 0.0
        if hasattr(engine, "on_download_progress"):
            engine.on_download_progress = self._download_progress
        self._thread = QThread()
        self._thread.setObjectName("model-worker")
        self.moveToThread(self._thread)
        self.request_load.connect(self._load)
        self.request_transcribe.connect(self._transcribe)
        self.request_live.connect(self._live)
        self.request_dictate.connect(self._dictate)
        self._thread.start()

    def transcribe(self, audio, options: TranscribeOptions) -> None:
        """Queues a transcription. The cancel flag is reset here, at request time,
        so a cancel clicked while the request waits in the queue is not lost."""
        self._cancel.clear()
        self.request_transcribe.emit(audio, options)

    def start_live(self, source, options: TranscribeOptions) -> None:
        """Queues a live session that reads source.drain() until stop_live()."""
        self._live_stop.clear()
        self.request_live.emit(source, options)

    def dictate(self, audio, options: TranscribeOptions, job: int) -> None:
        """Queues a dictation; the answer is dictation_finished / dictation_failed."""
        self.request_dictate.emit(audio, options, job)

    def stop_live(self) -> None:
        """Thread-safe: ends the live session after a final pass."""
        self._live_stop.set()

    def cancel(self) -> None:
        """Thread-safe: stops the running transcription after the current segment."""
        self._cancel.set()

    def shutdown(self) -> None:
        self.cancel()
        self.stop_live()
        self._thread.quit()
        self._thread.wait()

    def _download_progress(self, spec, done: int, total: int) -> None:
        now = time.monotonic()
        if done < total and now - self._last_download_emit < 0.15:
            return  # a few updates per second are plenty for a progress bar
        self._last_download_emit = now
        self.model_downloading.emit(spec.model_name, done, total)

    @Slot(str)
    def _load(self, key: str) -> None:
        spec = get_model(key)
        if self._engine.model == spec:
            return
        self.model_loading.emit(spec.label)
        try:
            self._engine.load(spec)
        except Exception as exc:
            log.exception("Model load failed")
            self.error.emit(f"Impossible de charger {spec.model_name} : {exc}")
            return
        self.model_loaded.emit(spec.key, self._engine.device.description)

    @Slot(object, object)
    def _transcribe(self, audio, options: TranscribeOptions) -> None:
        if self._cancel.is_set():
            self.transcription_finished.emit(0.0, 0.0, True)
            return
        start = time.perf_counter()
        try:
            info, segments = self._engine.transcribe(audio, options)
            self.transcription_started.emit(info)
            for segment in segments:
                if self._cancel.is_set():
                    break
                self.segment_ready.emit(segment)
        except Exception as exc:
            log.exception("Transcription failed")
            self.error.emit(f"Échec de la transcription : {exc}")
            return
        self.transcription_finished.emit(
            time.perf_counter() - start, info.duration, self._cancel.is_set()
        )

    @Slot(object, object)
    def _live(self, source, options: TranscribeOptions) -> None:
        # A loop inside the worker thread: the engine keeps a single owner.
        try:
            live = self._live_factory(self._engine, options)
            while not self._live_stop.is_set():
                live.feed(source.drain())
                if not live.ready():
                    self._live_stop.wait(self.LIVE_POLL_S)
                    continue
                start = time.perf_counter()
                update = live.step()
                if update is not None:
                    self.live_update.emit(update, time.perf_counter() - start)
            live.feed(source.drain())
            self.live_update.emit(live.flush(), 0.0)
        except Exception as exc:
            log.exception("Live transcription failed")
            self.error.emit(f"Échec de la transcription en direct : {exc}")
        self.live_finished.emit()

    @Slot(object, object, int)
    def _dictate(self, audio, options: TranscribeOptions, job: int) -> None:
        try:
            info, segments = self._engine.transcribe(audio, options)
            text = " ".join(s.text for s in segments if s.text)
        except Exception as exc:
            log.exception("Dictation failed")
            self.dictation_failed.emit(job, f"Échec de la dictée : {exc}")
            return
        self.dictation_finished.emit(job, text.strip(), info.language)
