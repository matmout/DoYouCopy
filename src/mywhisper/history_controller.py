"""History of the main window: which entry holds the current result, and when to save it.

Free of Qt Widgets, like SessionController: the window shows what this controller
says, and the whole policy (autosave of long sessions, audio kept or not, dictations
kept or not, the entry being edited) runs in tests without a window.

The current entry is the one the transcript shows: a new capture starts without
one, its first save creates it, later saves (autosave, final save, corrections)
update it in place.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from mywhisper.config import Settings
from mywhisper.core.types import Segment
from mywhisper.session import SessionController, SessionResult
from mywhisper.storage.history import Entry, HistoryStore

log = logging.getLogger(__name__)

CAPTURE_TITLES = {"record": "Enregistrement", "live": "Direct"}
DICTATION_TITLE_CHARS = 60


class HistoryController(QObject):
    """Saves the session's results into a HistoryStore, which may be missing (None):
    every method is then a no-op, so the window needs no special case."""

    changed = Signal()  # entries added, updated or removed: lists must be refreshed
    current_changed = Signal(object)  # id of the entry the transcript shows, or None
    # A capture's audio is on disk (entry id, Path). Emitted from the encoding thread:
    # Qt delivers it queued, on the thread of the receivers.
    audio_kept = Signal(int, object)

    def __init__(self, store: HistoryStore | None, settings: Settings) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self.current_id: int | None = None
        self._saved_count = 0  # segments of the current entry already saved

    @property
    def available(self) -> bool:
        """A store exists (it could be opened at startup)."""
        return self.store is not None

    @property
    def enabled(self) -> bool:
        """New results are saved (the user may turn the history off)."""
        return self.store is not None and self.settings.history_enabled

    # ---- current entry ---------------------------------------------------

    def new_entry(self) -> None:
        """A new capture or file starts: its first save will create a new entry."""
        self.current_id = None
        self._saved_count = 0
        self.current_changed.emit(None)

    def set_current(self, entry_id: int | None) -> None:
        self.current_id = entry_id
        self.current_changed.emit(entry_id)

    def entry(self, entry_id: int) -> Entry | None:
        return self.store.get(entry_id) if self.store is not None else None

    # ---- saving ------------------------------------------------------------

    def save(self, result: SessionResult) -> None:
        """Creates the current entry, or updates it. Errors are logged, never raised:
        a full disk must not interrupt a transcription."""
        if not self.enabled:
            return
        title = result.name if result.kind == "file" else CAPTURE_TITLES.get(result.kind, result.name)
        try:
            self.current_id = self.store.save(
                kind=result.kind,
                title=title,
                segments=result.segments,
                entry_id=self.current_id,
                source=str(result.source_path or ""),
                model=result.model_key,
                language=result.language,
                duration=result.duration,
            )
        except Exception:
            log.exception("Could not save the history")
            return
        self._saved_count = len(result.segments)
        self.current_changed.emit(self.current_id)
        self.changed.emit()

    def autosave(self, session: SessionController) -> None:
        """Called periodically: saves a running session if it produced new segments,
        so that a crash during a long meeting loses a few seconds, not the meeting."""
        if session.idle or not self.enabled or len(session.segments) == self._saved_count:
            return
        self.save(session.result())

    def record(self, result: SessionResult | None) -> None:
        """A transcription ended: final save, then its audio if the user keeps it.
        The audio is encoded on a background thread; audio_kept tells when it is ready."""
        if result is None or not self.enabled:
            return
        self.save(result)
        if self.current_id is None or result.audio is None or not self.settings.history_keep_audio:
            return
        try:
            self.store.attach_audio(self.current_id, result.audio, on_written=self.audio_kept.emit)
        except Exception:
            log.exception("Could not keep the audio")
        self.changed.emit()

    def record_dictation(self, text: str) -> None:
        """Universal dictation: its text only (never the audio), if the user keeps them.
        It never becomes the current entry: the window is not showing it."""
        text = text.strip()
        if not (self.enabled and self.settings.history_dictation and text):
            return
        try:
            self.store.save(
                kind="dictation",
                title=text.splitlines()[0][:DICTATION_TITLE_CHARS],
                segments=[Segment(0.0, 0.0, text)],
                model=self.settings.model_key,
            )
        except Exception:
            log.exception("Could not save the dictation")
            return
        self.changed.emit()

    def save_corrections(self, segments: list[Segment]) -> None:
        """The current result was edited or partly re-transcribed."""
        if self.current_id is None or self.store is None:
            return
        try:
            self.store.update_segments(self.current_id, segments)
        except Exception:
            log.exception("Could not save the corrections")

    # ---- removal -------------------------------------------------------------

    def forget(self, entry_id: int) -> None:
        """entry_id was deleted from the history panel."""
        if entry_id == self.current_id:
            self.current_id = None

    def clear(self) -> None:
        """Erases every entry and its audio. Files still open elsewhere (the player)
        cannot be deleted on Windows: the caller releases them first."""
        if self.store is None:
            return
        self.store.clear()
        self.current_id = None
        self.changed.emit()

    def purge_audio(self, older_than_days: int) -> None:
        """Retention changed: applies it at once."""
        if self.store is None:
            return
        self.store.purge_audio(older_than_days)
        self.changed.emit()

    @property
    def folder(self) -> Path | None:
        return self.store.folder if self.store is not None else None

    def count(self) -> int | None:
        return self.store.count() if self.store is not None else None

    def close(self) -> None:
        """Waits for the audio being encoded, then closes the database."""
        if self.store is not None:
            self.store.close()
