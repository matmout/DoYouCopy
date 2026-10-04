"""The transcription session of the main window: capture, transcription, current result.

Free of Qt Widgets: the window only displays what this controller tells it, so the
whole cycle (record -> transcribe, live, file, cancel, errors) runs in tests with a
fake recorder and a fake engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal

from mywhisper.audio.recorder import MicRecorder
from mywhisper.audio.sources import MIC, make_recorder
from mywhisper.config import Settings
from mywhisper.core.live import LiveUpdate, merge_sentences
from mywhisper.core.textproc import apply_replacements
from mywhisper.core.types import SAMPLE_RATE, AudioSource, Segment
from mywhisper.options import FILE, LIVE, live_config, transcribe_options

log = logging.getLogger(__name__)

MIN_RECORDING_S = 0.3

RECORD, LIVE_KIND, FILE_KIND = "record", "live", "file"


@dataclass
class SessionResult:
    """A finished transcription, as handed to the history."""

    kind: str  # "record", "live" or "file"
    name: str  # file stem, or a generic name for captures
    segments: list[Segment]
    language: str | None
    duration: float  # audio seconds
    model_key: str
    source_path: Path | None = None  # the imported file
    audio: np.ndarray | None = None  # 16 kHz mono samples of a microphone capture (float32 or int16)


class _Tee:
    """Live source that keeps a copy of what the live transcriber drains (int16, half the memory)."""

    def __init__(self, source) -> None:
        self.source = source
        self.chunks: list[np.ndarray] = []

    def drain(self) -> np.ndarray:
        samples = self.source.drain()
        if samples.size:
            self.chunks.append((np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16))
        return samples

    def audio(self) -> np.ndarray | None:
        return np.concatenate(self.chunks) if self.chunks else None


class SessionController(QObject):
    """State of the main window's session, driven by the window, answered by the worker."""

    changed = Signal()  # a state flag changed: the window refreshes its controls
    status = Signal(str, int)  # text, timeout in ms (0: stays)
    error = Signal(str, bool)  # message, retry of the model load possible
    capture_started = Signal(str)  # "record" or "live"
    capture_stopped = Signal()
    transcription_started = Signal()  # the transcript restarts from scratch
    segment_added = Signal(object, object)  # Segment, progress fraction or None
    live_updated = Signal(object, str)  # committed segments, provisional text
    finished = Signal(object)  # SessionResult, or None (cancelled, too short, failed)
    segments_edited = Signal()  # the current segments changed after the fact (edit, re-transcription)
    model_loading = Signal(str)  # model label
    model_downloading = Signal(str, object, object)  # model name, done bytes, total bytes (object: Qt int is 32-bit, models exceed 2 GB)
    model_loaded = Signal(str, str)  # model key, device description

    def __init__(self, settings: Settings, worker, recorder=None, recorder_factory=make_recorder) -> None:
        super().__init__()
        self.settings = settings
        self.worker = worker
        # A given recorder is kept; otherwise one is made for settings.audio_source at each capture.
        self._recorder = recorder or MicRecorder(settings.input_device)
        self._factory = None if recorder is not None else recorder_factory
        self._recorder_source = MIC
        self.segments: list[Segment] = []
        self.source_name = "transcription"
        self.busy = False  # file / recording transcription in progress
        self.live = False  # live session running (or finishing its final pass)
        self.live_stopping = False
        self.model_ready = False
        self.model_loading_now = False
        self.duration = 0.0
        self.language: str | None = None
        self._kind = FILE_KIND
        self._source_path: Path | None = None
        self._audio: np.ndarray | None = None
        self._tee: _Tee | None = None
        self.retranscribing = False
        self._retranscribe_job = 0
        self._retranscribe_range = (0, 0)

        w = worker
        w.model_loading.connect(self._on_model_loading)
        w.model_downloading.connect(self.model_downloading)
        w.model_loaded.connect(self._on_model_loaded)
        w.transcription_started.connect(self._on_started)
        w.segment_ready.connect(self._on_segment)
        w.transcription_finished.connect(self._on_finished)
        w.live_update.connect(self._on_live_update)
        w.live_finished.connect(self._on_live_finished)
        w.error.connect(self._on_error)
        w.retranscribed.connect(self._on_retranscribed)
        w.retranscribe_failed.connect(self._on_retranscribe_failed)

    # ---- state ---------------------------------------------------------

    @property
    def recorder(self):
        return self._recorder

    @recorder.setter
    def recorder(self, recorder) -> None:
        self._recorder = recorder
        self._factory = None

    @property
    def idle(self) -> bool:
        return not (self.busy or self.live or self.retranscribing)

    @property
    def recording(self) -> bool:
        """Microphone open for a recording (not a live session)."""
        return self.recorder.is_recording and not self.live

    @property
    def capturing(self) -> bool:
        return self.recording or self.live

    @property
    def keeps_audio(self) -> bool:
        return self.settings.history_enabled and self.settings.history_keep_audio

    @property
    def available(self) -> bool:
        """Nothing running: a new capture or file can start."""
        return self.idle and not self.recorder.is_recording

    # ---- model ---------------------------------------------------------

    def load_model(self, key: str) -> None:
        self.model_ready = False
        self.worker.request_load.emit(key)

    def reconfigure(self, key: str, **engine_kwargs) -> None:
        self.model_ready = False
        self.worker.reconfigure(key, **engine_kwargs)

    # ---- capture -------------------------------------------------------

    def _open_input(self) -> bool:
        source = self.settings.audio_source
        if self._factory is not None and source != self._recorder_source:
            self._recorder = self._factory(source, self.settings.input_device)
            self._recorder_source = source
        self._recorder.device_name = self.settings.input_device
        try:
            self._recorder.start()
        except Exception as exc:
            log.exception("Audio capture start failed")
            if source == MIC or self._factory is None:
                self.error.emit(f"Impossible d'ouvrir le micro : {exc}", False)
            else:
                self.error.emit(f"Impossible de démarrer la capture : {exc}", False)
            return False
        return True

    def toggle_recording(self) -> None:
        if self.recorder.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> bool:
        if not self.available or not self._open_input():
            return False
        self.capture_started.emit(RECORD)
        self.status.emit("Enregistrement…", 0)
        self.changed.emit()
        return True

    def stop_recording(self) -> None:
        if not self.recording:
            return
        audio = self.recorder.stop()
        self.capture_stopped.emit()
        self.changed.emit()
        if audio.size < MIN_RECORDING_S * SAMPLE_RATE:
            self.status.emit("Enregistrement trop court.", 4000)
            self.finished.emit(None)
            return
        self._transcribe(audio, RECORD, "dictee", samples=audio if self.keeps_audio else None)

    def start_live(self) -> bool:
        if not self.available or not self._open_input():
            return False
        self.live = True
        self.live_stopping = False
        self.segments = []
        self.source_name = "direct"
        self._kind = LIVE_KIND
        self._source_path = None
        self._audio = None
        self.language = self.settings.language
        self.capture_started.emit(LIVE_KIND)
        self.changed.emit()
        self.worker.live_config = live_config(self.settings)
        source = self.recorder
        self._tee = None
        if self.keeps_audio:
            source = self._tee = _Tee(self.recorder)
        self.worker.start_live(source, transcribe_options(self.settings, LIVE))
        return True

    def stop_live(self) -> None:
        if not self.live or self.live_stopping:
            return
        self.live_stopping = True
        self.status.emit("Fin du direct…", 0)
        self.worker.stop_live()
        self.changed.emit()

    # ---- transcription -------------------------------------------------

    def transcribe_file(self, path: Path) -> bool:
        if not self.available:
            return False
        self._transcribe(path, FILE_KIND, path.stem, source_path=path)
        return True

    def _transcribe(
        self,
        audio: AudioSource,
        kind: str,
        name: str,
        source_path: Path | None = None,
        samples: np.ndarray | None = None,
    ) -> None:
        self.segments = []
        self.source_name = name
        self._kind = kind
        self._source_path = source_path
        self._audio = samples
        self.language = None
        self.busy = True
        self.duration = 0.0
        self.transcription_started.emit()
        self.changed.emit()
        self.status.emit("Analyse de l'audio…" if self.model_ready else "En attente du modèle…", 0)
        self.worker.transcribe(audio, transcribe_options(self.settings, FILE))

    def cancel(self) -> None:
        self.worker.cancel()

    def open(self, segments: list[Segment], name: str, language: str | None = None) -> bool:
        """Shows a past transcription (history) as the current result.

        Only segments, name and language are replaced: result() is meant for a capture
        or file just transcribed, an opened entry is saved back through its history id."""
        if not self.available:
            return False
        self.segments = list(segments)
        self.source_name = name
        self.language = language
        self.status.emit("", 0)
        self.changed.emit()
        return True

    def clear(self) -> None:
        self.segments = []
        self.status.emit("", 0)
        self.changed.emit()

    # ---- corrections -------------------------------------------------------

    def edit_texts(self, texts: list[str]) -> bool:
        """New text of each segment (same count, same order). The times are kept; the word
        timings of a changed segment are dropped, they no longer match. True if anything changed."""
        if len(texts) != len(self.segments):
            raise ValueError("one text per segment")
        changed = False
        for i, (segment, typed) in enumerate(zip(self.segments, texts, strict=True)):
            text = typed.strip()
            if text != segment.text:
                self.segments[i] = replace(segment, text=text, words=())
                changed = True
        if changed:
            self.segments_edited.emit()
            self.changed.emit()
        return changed

    def retranscribe(self, audio_path: Path, first: int, last: int, model_key: str = "precise") -> bool:
        """Transcribes segments first..last again from the audio, with another model."""
        if not self.available or not self.segments or not 0 <= first <= last < len(self.segments):
            return False
        start = max(0.0, self.segments[first].start - 0.2)
        end = self.segments[last].end + 0.2
        self.retranscribing = True
        self._retranscribe_job += 1
        self._retranscribe_range = (first, last)
        options = replace(transcribe_options(self.settings, FILE), language=self.language or self.settings.language)
        self.worker.retranscribe(audio_path, start, end, options, model_key, self._retranscribe_job)
        self.status.emit("Retranscription du passage…", 0)
        self.changed.emit()
        return True

    def _on_retranscribed(self, job: int, segments: list[Segment]) -> None:
        if job != self._retranscribe_job or not self.retranscribing:
            return
        self.retranscribing = False
        first, last = self._retranscribe_range
        segments = [self.apply_vocabulary(s) for s in segments if s.text]
        if segments:
            self.segments[first : last + 1] = segments
            self.status.emit("Passage retranscrit.", 5000)
            self.segments_edited.emit()
        else:
            self.status.emit("Aucune parole retrouvée dans ce passage.", 5000)
        self.changed.emit()

    def _on_retranscribe_failed(self, job: int, message: str) -> None:
        if job != self._retranscribe_job:
            return
        self.retranscribing = False
        self.status.emit("", 0)
        self.error.emit(message, False)
        self.changed.emit()

    def apply_vocabulary(self, segment: Segment) -> Segment:
        if not self.settings.replacements:
            return segment
        return replace(segment, text=apply_replacements(segment.text, self.settings.replacements))

    def result(self) -> SessionResult:
        return SessionResult(
            kind=self._kind,
            name=self.source_name,
            segments=list(self.segments),
            language=self.language,
            duration=self.duration or (self.segments[-1].end if self.segments else 0.0),
            model_key=self.settings.model_key,
            source_path=self._source_path,
            audio=self._audio,
        )

    def shutdown(self) -> None:
        self.worker.stop_live()
        if self.recorder.is_recording:
            self.recorder.stop()

    # ---- worker callbacks ----------------------------------------------

    def _on_model_loading(self, label: str) -> None:
        self.model_loading_now = True
        self.model_ready = False
        self.model_loading.emit(label)
        self.status.emit("Chargement du modèle…", 0)
        self.changed.emit()

    def _on_model_loaded(self, key: str, device_description: str) -> None:
        self.model_loading_now = False
        self.model_ready = True
        self.model_loaded.emit(key, device_description)
        self.changed.emit()

    def _on_started(self, info) -> None:
        self.duration = info.duration
        self.language = info.language
        self.status.emit(f"Transcription en cours ({info.language}, {clock(info.duration)})", 0)

    def _on_segment(self, segment: Segment) -> None:
        segment = self.apply_vocabulary(segment)
        self.segments.append(segment)
        progress = segment.end / self.duration if self.duration else None
        self.segment_added.emit(segment, progress)
        self.changed.emit()

    def _on_finished(self, elapsed: float, duration: float, cancelled: bool) -> None:
        self.busy = False
        self.changed.emit()
        if cancelled:
            self.status.emit("Transcription annulée.", 5000)
            self.finished.emit(None)
            return
        speed = f" · {duration / elapsed:.0f}× temps réel" if elapsed and duration else ""
        self.status.emit(f"{clock(duration)} transcrit en {elapsed:.1f} s{speed}", 0)
        self.finished.emit(self.result() if self.segments else None)

    def _on_live_update(self, update: LiveUpdate, pass_seconds: float) -> None:
        if not self.live:
            return
        committed = [self.apply_vocabulary(s) for s in update.committed]
        self.segments.extend(committed)
        self.live_updated.emit(committed, update.provisional)
        if pass_seconds:
            self.status.emit(f"passe {pass_seconds:.2f} s", 0)
        self.changed.emit()

    def _on_live_finished(self) -> None:
        self.live = False
        self.live_stopping = False
        self.recorder.stop()
        self.capture_stopped.emit()
        self.segments = merge_sentences(self.segments)
        if self._tee is not None:
            self._audio, self._tee = self._tee.audio(), None
        self.status.emit(f"Direct terminé · {len(self.segments)} phrase(s)", 6000)
        self.changed.emit()
        self.finished.emit(self.result() if self.segments else None)

    def _on_error(self, message: str) -> None:
        failed_load = self.model_loading_now
        self.model_loading_now = False
        self.busy = False
        self.status.emit("", 0)
        self.error.emit(message, failed_load)
        self.changed.emit()


def clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"
