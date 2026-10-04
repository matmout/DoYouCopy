from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from mywhisper.core.engine import TranscriptionEngine
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

    model_loading = Signal(str)  # model label
    model_loaded = Signal(str, str)  # model key, device description
    transcription_started = Signal(object)  # TranscriptionInfo
    segment_ready = Signal(object)  # Segment
    transcription_finished = Signal(float, float, bool)  # elapsed s, audio s, cancelled
    error = Signal(str)

    def __init__(self, engine: TranscriptionEngine) -> None:
        super().__init__()
        self._engine = engine
        self._cancel = threading.Event()
        self._thread = QThread()
        self._thread.setObjectName("model-worker")
        self.moveToThread(self._thread)
        self.request_load.connect(self._load)
        self.request_transcribe.connect(self._transcribe)
        self._thread.start()

    def transcribe(self, audio, options: TranscribeOptions) -> None:
        """Queues a transcription. The cancel flag is reset here, at request time,
        so a cancel clicked while the request waits in the queue is not lost."""
        self._cancel.clear()
        self.request_transcribe.emit(audio, options)

    def cancel(self) -> None:
        """Thread-safe: stops the running transcription after the current segment."""
        self._cancel.set()

    def shutdown(self) -> None:
        self.cancel()
        self._thread.quit()
        self._thread.wait()

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
