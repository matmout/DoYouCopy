"""The model thread: every use of the engine (load, transcribe, live, dictation).

Threading contract, the key point for an audit:
- requests come from the GUI thread through queued signals (request_*), so the
  worker handles them one at a time, in order: the GPU has a single user;
- answers go back as signals, delivered on the GUI thread;
- only cancel() and stop_live() touch the worker from outside, through
  threading.Event flags; nothing else is shared between the threads;
- the model is also freed on this thread, by shutdown(): freeing a GPU model of
  the ROCm build of CTranslate2 from another thread, once this one has ended,
  kills the process (exit code 127, sometimes a native stack trace);
- after a CPU model of that build, the thread can never end at all (see
  FasterWhisperEngine.pins_its_thread): shutdown() then leaves it running, and
  the app ends the process with os._exit (app.main).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from mywhisper.core.engine import TranscriptionEngine
from mywhisper.core.live import LiveTranscriber
from mywhisper.core.models import get_model
from mywhisper.core.types import SAMPLE_RATE, Segment, TranscribeOptions, Word

log = logging.getLogger(__name__)


def load_clip(path: str, start: float, end: float):
    """16 kHz mono samples of [start, end] seconds of an audio or video file."""
    from faster_whisper.audio import decode_audio

    audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
    return audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)]


def shift_segment(segment: Segment, offset: float) -> Segment:
    words = tuple(Word(w.start + offset, w.end + offset, w.text, w.probability) for w in segment.words)
    return Segment(segment.start + offset, segment.end + offset, segment.text, words)


class ModelWorker(QObject):
    """Owns the engine on a dedicated thread: one GPU user, a UI that never freezes.

    Requests arrive through the queued request_* signals, so they run one after
    another in the order they were sent.
    """

    request_load = Signal(str)
    request_transcribe = Signal(object, object)  # AudioSource, TranscribeOptions
    request_live = Signal(object, object)  # source with drain(), TranscribeOptions
    request_dictate = Signal(object, object, int)  # audio, TranscribeOptions, job id
    request_reconfigure = Signal(object, str)  # engine.configure() kwargs, model key to reload
    request_retranscribe = Signal(object, float, float, object, str, int)  # path, start, end, options, key, job
    request_unload = Signal()  # blocking: the caller waits until the model is freed

    model_loading = Signal(str)  # model label
    model_downloading = Signal(str, object, object)  # model name, done bytes, total bytes (object: Qt int is 32-bit, models exceed 2 GB)
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
    # re-transcription of a passage: segments with times in the whole audio
    retranscribed = Signal(int, object)  # job id, list[Segment]
    retranscribe_failed = Signal(int, str)  # job id, message

    LIVE_POLL_S = 0.05

    def __init__(
        self,
        engine: TranscriptionEngine,
        live_factory: Callable[..., LiveTranscriber] = LiveTranscriber,
        clip_loader: Callable[[str, float, float], object] = load_clip,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._live_factory = live_factory
        self._clip_loader = clip_loader
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
        self.request_reconfigure.connect(self._reconfigure)
        self.request_retranscribe.connect(self._retranscribe)
        self.request_unload.connect(self._unload, Qt.ConnectionType.BlockingQueuedConnection)
        self.live_config = None  # LiveConfig for the next live session (None: defaults)
        self.ended = False  # the thread has stopped (set by shutdown)
        self._shut_down = False
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

    def retranscribe(self, path, start: float, end: float, options: TranscribeOptions, key: str, job: int) -> None:
        """Queues the transcription of [start, end] of an audio file with model key; the
        current model is loaded back afterwards. Answer: retranscribed / retranscribe_failed."""
        self.request_retranscribe.emit(path, start, end, options, key, job)

    def stop_live(self) -> None:
        """Thread-safe: ends the live session after a final pass."""
        self._live_stop.set()

    def cancel(self) -> None:
        """Thread-safe: stops the running transcription after the current segment."""
        self._cancel.set()

    def shutdown(self) -> bool:
        """Stops the running job, frees the model on this worker's thread, then ends
        the thread. Blocks until done; safe to call more than once.

        Returns self.ended. False when the engine pins its thread (CPU model of the
        ROCm build): the thread is left running, idle, since waiting for its end would
        hang forever; the caller must then end the process with os._exit."""
        if self._shut_down:
            return self.ended
        self._shut_down = True
        self.cancel()
        self.stop_live()
        self.request_unload.emit()  # runs after the job in progress, which now ends quickly
        if getattr(self._engine, "pins_its_thread", False):
            log.info("Model thread left running: its end would deadlock in CTranslate2")
            return False
        self._thread.quit()
        self._thread.wait()
        self.ended = True
        return True

    @Slot()
    def _unload(self) -> None:
        try:
            self._engine.unload()
        except Exception:
            log.exception("Model unload failed")

    def _download_progress(self, spec, done: int, total: int) -> None:
        now = time.monotonic()
        if done < total and now - self._last_download_emit < 0.15:
            return  # a few updates per second are plenty for a progress bar
        self._last_download_emit = now
        self.model_downloading.emit(spec.model_name, done, total)

    def reconfigure(self, key: str, **engine_kwargs) -> None:
        """Device, threads or models folder changed: applied between two jobs, then reload."""
        self.request_reconfigure.emit(engine_kwargs, key)

    @Slot(object, str)
    def _reconfigure(self, engine_kwargs: dict, key: str) -> None:
        try:
            self._engine.configure(**engine_kwargs)
        except Exception as exc:
            log.exception("Engine reconfiguration failed")
            self.error.emit(f"Impossible d'appliquer les réglages : {exc}")
            return
        self._load(key)

    @Slot(str)
    def _load(self, key: str) -> None:
        """Loads the window's model and reports it (model_loading, model_loaded or error)."""
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
            extra = {"config": self.live_config} if self.live_config is not None else {}
            live = self._live_factory(self._engine, options, **extra)
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

    @Slot(object, float, float, object, str, int)
    def _retranscribe(self, path, start: float, end: float, options: TranscribeOptions, key: str, job: int) -> None:
        # The passage model is a temporary guest: it is loaded silently (no model_loading /
        # model_loaded / error), so the window neither shows it as its model nor reports a
        # failure twice. Only the reload of the window's own model is announced.
        previous = self._engine.model
        try:
            clip = self._clip_loader(str(path), start, end)
            spec = get_model(key)
            if self._engine.model != spec:
                self._engine.load(spec)
            _, segments = self._engine.transcribe(clip, options)
            result = [shift_segment(s, start) for s in segments]
        except Exception as exc:
            log.exception("Re-transcription failed")
            self.retranscribe_failed.emit(job, f"Échec de la retranscription : {exc}")
            result = None
        if previous is not None and self._engine.model != previous:
            self._load(previous.key)
        if result is not None:
            self.retranscribed.emit(job, result)

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
