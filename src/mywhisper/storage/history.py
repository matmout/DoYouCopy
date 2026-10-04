"""Local history of transcriptions: SQLite with FTS5 full-text search.

One row per session (text, segments with their words, metadata), the audio of
microphone captures as a file beside the database. Free of Qt, used from the GUI
thread only; the audio is encoded on a background thread.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from mywhisper.core.types import Segment, Word
from mywhisper.storage.audio import write_audio

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    created REAL NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    language TEXT,
    duration REAL NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    audio_path TEXT,
    text TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS sessions_created ON sessions(created);
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    title, text, content='sessions', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
    INSERT INTO sessions_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;
CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
END;
CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE OF title, text ON sessions BEGIN
    INSERT INTO sessions_fts(sessions_fts, rowid, title, text) VALUES ('delete', old.id, old.title, old.text);
    INSERT INTO sessions_fts(rowid, title, text) VALUES (new.id, new.title, new.text);
END;
"""

KIND_LABELS = {"record": "Micro", "live": "Direct", "file": "Fichier", "dictation": "Dictée"}
MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


@dataclass
class Entry:
    id: int
    created: float  # epoch seconds
    title: str
    kind: str  # "record", "live", "file" or "dictation"
    source: str = ""  # path of the imported file
    model: str = ""
    language: str | None = None
    duration: float = 0.0
    favorite: bool = False
    audio_path: str | None = None
    text: str = ""
    snippet: str = ""  # search result context, with « » around the matches
    segments: list[Segment] = field(default_factory=list)  # filled by HistoryStore.get()

    @property
    def audio(self) -> Path | None:
        """The kept audio, once written to disk (FLAC, or WAV if FLAC encoding failed)."""
        if not self.audio_path:
            return None
        path = Path(self.audio_path)
        return next((p for p in (path, path.with_suffix(".wav")) if p.is_file()), None)

    def date_label(self) -> str:
        t = time.localtime(self.created)
        return f"{t.tm_mday} {MONTHS[t.tm_mon - 1]} {t.tm_year} · {t.tm_hour:02d}:{t.tm_min:02d}"


# ---- segments <-> JSON ------------------------------------------------------


def segments_to_json(segments: list[Segment]) -> str:
    data = []
    for s in segments:
        item = {"start": s.start, "end": s.end, "text": s.text}
        if s.words:
            item["words"] = [_word_to_list(w) for w in s.words]
        data.append(item)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _word_to_list(w: Word) -> list:
    values = [round(w.start, 3), round(w.end, 3), w.text]
    return values if w.probability is None else [*values, round(w.probability, 3)]


def segments_from_json(text: str) -> list[Segment]:
    segments = []
    for item in json.loads(text or "[]"):
        words = tuple(_word_from_list(values) for values in item.get("words", ()))
        segments.append(Segment(item["start"], item["end"], item["text"], words))
    return segments


def _word_from_list(values: list) -> Word:
    return Word(*values[:4])


def fts_query(text: str) -> str:
    """User words -> FTS5 query: every word must appear, as a prefix ("rocm" finds "ROCm7")."""
    terms = [t.replace('"', "") for t in text.split()]
    return " ".join(f'"{t}"*' for t in terms if t)


# ---- store ---------------------------------------------------------------------


class HistoryStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.audio_dir = folder / "audio"
        folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(folder / "history.db"))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")  # a crash keeps what was committed
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.db.commit()
        self._writers: list[threading.Thread] = []

    def close(self) -> None:
        self.wait_for_audio()
        self.db.close()

    # ---- writing ---------------------------------------------------------

    def save(
        self,
        *,
        kind: str,
        title: str,
        segments: list[Segment],
        entry_id: int | None = None,
        source: str = "",
        model: str = "",
        language: str | None = None,
        duration: float = 0.0,
        created: float | None = None,
    ) -> int:
        """Inserts a session, or updates entry_id (autosave of a long session). Returns its id."""
        text = "\n".join(s.text for s in segments if s.text)
        data = segments_to_json(segments)
        if entry_id is not None:
            cursor = self.db.execute(
                "UPDATE sessions SET text=?, segments=?, language=?, duration=?, model=? WHERE id=?",
                (text, data, language, duration, model, entry_id),
            )
            if cursor.rowcount:
                self.db.commit()
                return entry_id
        cursor = self.db.execute(
            "INSERT INTO sessions(created, title, kind, source, model, language, duration, text, segments)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (created or time.time(), title, kind, source, model, language, duration, text, data),
        )
        self.db.commit()
        return cursor.lastrowid

    def update_segments(self, entry_id: int, segments: list[Segment]) -> None:
        """After an edit of the transcript."""
        text = "\n".join(s.text for s in segments if s.text)
        self.db.execute(
            "UPDATE sessions SET text=?, segments=? WHERE id=?", (text, segments_to_json(segments), entry_id)
        )
        self.db.commit()

    def attach_audio(
        self,
        entry_id: int,
        samples: np.ndarray,
        wait: bool = False,
        on_written: Callable[[int, Path], None] | None = None,
    ) -> Path:
        """Keeps the capture's audio; encoded on a background thread unless wait.
        on_written(entry_id, path) is called from that thread once the file is complete."""
        target = self.audio_dir / f"{entry_id}.flac"
        self.db.execute("UPDATE sessions SET audio_path=? WHERE id=?", (str(target), entry_id))
        self.db.commit()

        def write() -> None:
            try:
                written = write_audio(target, samples)
            except Exception:
                log.exception("Could not keep the audio of session %s", entry_id)
                return
            if on_written is not None:
                on_written(entry_id, written)

        if wait:
            write()
        else:
            thread = threading.Thread(target=write, name=f"history-audio-{entry_id}", daemon=True)
            self._writers = [t for t in self._writers if t.is_alive()] + [thread]
            thread.start()
        return target

    def wait_for_audio(self) -> None:
        for thread in self._writers:
            thread.join()
        self._writers = []

    def rename(self, entry_id: int, title: str) -> None:
        self.db.execute("UPDATE sessions SET title=? WHERE id=?", (title.strip() or "Sans titre", entry_id))
        self.db.commit()

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        self.db.execute("UPDATE sessions SET favorite=? WHERE id=?", (int(favorite), entry_id))
        self.db.commit()

    def delete(self, entry_id: int) -> None:
        row = self.db.execute("SELECT audio_path FROM sessions WHERE id=?", (entry_id,)).fetchone()
        self.db.execute("DELETE FROM sessions WHERE id=?", (entry_id,))
        self.db.commit()
        if row is not None:
            self._remove_audio(row["audio_path"])

    def clear(self) -> None:
        """Erases the whole history, audio included."""
        self.wait_for_audio()
        rows = self.db.execute("SELECT audio_path FROM sessions WHERE audio_path IS NOT NULL").fetchall()
        self.db.execute("DELETE FROM sessions")
        self.db.commit()
        for row in rows:
            self._remove_audio(row["audio_path"])
        self.db.execute("VACUUM")

    def purge_audio(self, older_than_days: int, now: float | None = None) -> int:
        """Retention: removes the audio of sessions older than N days, keeps their text."""
        if older_than_days <= 0:
            return 0
        limit = (now or time.time()) - older_than_days * 86400
        rows = self.db.execute(
            "SELECT id, audio_path FROM sessions WHERE audio_path IS NOT NULL AND created < ?", (limit,)
        ).fetchall()
        for row in rows:
            self._remove_audio(row["audio_path"])
            self.db.execute("UPDATE sessions SET audio_path=NULL WHERE id=?", (row["id"],))
        self.db.commit()
        return len(rows)

    @staticmethod
    def _remove_audio(path: str | None) -> None:
        if not path:
            return
        for candidate in (Path(path), Path(path).with_suffix(".wav")):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not delete %s", candidate)

    # ---- reading ---------------------------------------------------------

    COLUMNS = ("id", "created", "title", "kind", "source", "model", "language", "duration", "favorite", "audio_path")

    def list(self, query: str = "", favorites_only: bool = False, limit: int = 500) -> list[Entry]:
        """Newest first; with a query, only the sessions containing every word."""
        columns = ", ".join(f"s.{c}" for c in self.COLUMNS)
        favorite = " AND s.favorite = 1" if favorites_only else ""
        match = fts_query(query)
        if not match:
            sql = f"SELECT {columns}, '' AS snippet FROM sessions s WHERE 1{favorite} ORDER BY s.created DESC LIMIT ?"
            return [self._entry(row) for row in self.db.execute(sql, (limit,))]
        sql = (
            f"SELECT {columns}, snippet(sessions_fts, 1, '«', '»', '…', 12) AS snippet"
            " FROM sessions_fts JOIN sessions s ON s.id = sessions_fts.rowid"
            f" WHERE sessions_fts MATCH ?{favorite} ORDER BY s.created DESC LIMIT ?"
        )
        try:
            return [self._entry(row) for row in self.db.execute(sql, (match, limit))]
        except sqlite3.OperationalError:
            log.warning("Invalid search query")  # its words stay private
            return []

    def get(self, entry_id: int) -> Entry | None:
        row = self.db.execute(
            f"SELECT {', '.join(self.COLUMNS)}, text, segments, '' AS snippet FROM sessions WHERE id=?", (entry_id,)
        ).fetchone()
        if row is None:
            return None
        entry = self._entry(row)
        entry.text = row["text"]
        entry.segments = segments_from_json(row["segments"])
        return entry

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            created=row["created"],
            title=row["title"],
            kind=row["kind"],
            source=row["source"],
            model=row["model"],
            language=row["language"],
            duration=row["duration"],
            favorite=bool(row["favorite"]),
            audio_path=row["audio_path"],
            snippet=row["snippet"],
        )
