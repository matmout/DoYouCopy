"""Synchronised editor: word spans, playback highlight, edits, re-transcription of a passage."""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QTextCharFormat  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.types import SAMPLE_RATE, Segment, TranscriptionInfo, Word  # noqa: E402
from mywhisper.gpu.rocm_env import CPU  # noqa: E402
from mywhisper.session import SessionController  # noqa: E402
from mywhisper.storage.history import HistoryStore  # noqa: E402
from mywhisper.storage.audio import write_audio  # noqa: E402
from mywhisper.ui import theme  # noqa: E402
from mywhisper.ui.main_window import MainWindow  # noqa: E402
from mywhisper.ui.widgets.transcript_view import TranscriptView  # noqa: E402
from mywhisper.ui.workers import ModelWorker  # noqa: E402

from test_ui import FakeEngine, wait_until  # noqa: E402

TIMED = [
    Segment(0.0, 1.0, "Bonjour tout le monde.", (
        Word(0.0, 0.4, " Bonjour", 0.98), Word(0.4, 0.6, " tout", 0.95),
        Word(0.6, 0.7, " le", 0.9), Word(0.7, 1.0, " monde.", 0.3),
    )),
    Segment(1.5, 3.0, "Sans les mots."),
]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    v = TranscriptView(theme.DARK)
    v.resize(600, 400)
    v.render(TIMED, timestamps=True)
    v.show()
    yield v
    v.close()


def key(view, key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    view.editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


def test_words_are_found_highlighted_and_clickable(view):
    text = view.displayed_text()
    span = view.span_at_time(0.45)
    assert text[span.first:span.last] == "tout"
    assert view.span_at_time(2.0).first == text.index("Sans")  # segment without words: whole line
    assert view.span_at_time(1.35) is None  # in the gap between the two segments

    view.highlight_time(0.8)
    selection = view.editor.extraSelections()[0]
    assert selection.cursor.selectedText() == "monde."

    clicked = []
    view.word_clicked.connect(clicked.append)
    view._on_click(text.index("le monde") + 1)
    assert clicked == [0.6]


def test_doubtful_words_are_underlined(view):
    cursor = view.editor.textCursor()
    text = view.displayed_text()
    cursor.setPosition(text.index("monde") + 2)
    assert cursor.charFormat().underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    cursor.setPosition(text.index("Bonjour") + 2)
    assert cursor.charFormat().underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline


def test_edit_mode_keeps_one_line_per_segment(view):
    view.start_editing(TIMED)
    assert view.displayed_text() == "Bonjour tout le monde.\nSans les mots."  # no timestamps
    editor = view.editor
    cursor = editor.textCursor()
    cursor.setPosition(len("Bonjour tout le monde."))
    editor.setTextCursor(cursor)
    key(view, Qt.Key.Key_Return, "\r")
    key(view, Qt.Key.Key_Delete)  # would merge the two lines
    cursor.setPosition(len("Bonjour tout le monde.") + 1)
    editor.setTextCursor(cursor)
    key(view, Qt.Key.Key_Backspace)  # same
    assert editor.document().blockCount() == 2
    key(view, Qt.Key.Key_A, "A")  # ordinary typing works
    cursor.select(cursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    key(view, Qt.Key.Key_X, "x")  # a selection over both lines cannot be replaced
    assert view.stop_editing() == ["Bonjour tout le monde.", "ASans les mots."]
    assert editor.isReadOnly()


def test_selected_segments(view):
    cursor = view.editor.textCursor()
    text = view.displayed_text()
    cursor.setPosition(text.index("tout"))
    cursor.setPosition(text.index("mots"), cursor.MoveMode.KeepAnchor)
    view.editor.setTextCursor(cursor)
    assert view.selected_segments() == (0, 1)
    cursor.setPosition(text.index("mots"))
    view.editor.setTextCursor(cursor)
    assert view.selected_segments() == (1, 1)


def test_dictation_line_breaks_stay_in_one_block(app):
    v = TranscriptView(theme.DARK)
    v.render([Segment(0, 0, "Ligne un\nLigne deux")], timestamps=False)
    assert v.editor.document().blockCount() == 1
    assert v.edited_texts() == ["Ligne un\nLigne deux"]


# ---- session -----------------------------------------------------------------


class PassageEngine(FakeEngine):
    """Answers a re-transcription with times relative to the clip."""

    def transcribe(self, audio, options):
        self.clip, self.options = audio, options
        return TranscriptionInfo("fr", 0.99, 1.0), iter([Segment(0.2, 1.1, "Texte précis.", (Word(0.2, 1.1, " Texte", 0.99),))])


def make_session(app, engine, clips):
    worker = ModelWorker(engine, clip_loader=lambda path, start, end: clips.append((path, start, end)) or np.zeros(16000))
    session = SessionController(Settings(), worker)
    session.load_model("turbo")
    wait_until(app, lambda: session.model_ready)
    return session, worker


def test_edit_texts_keeps_times_and_drops_stale_words(app):
    session, worker = make_session(app, FakeEngine(), [])
    edited = []
    session.segments_edited.connect(lambda: edited.append(True))
    session.open(list(TIMED), "x")
    assert not session.edit_texts(["Bonjour tout le monde.", "  Sans les mots. "])  # unchanged
    assert session.edit_texts(["Bonjour à tous.", "Sans les mots."])
    assert session.segments[0] == Segment(0.0, 1.0, "Bonjour à tous.")
    assert session.segments[1] is TIMED[1] and edited == [True]
    with pytest.raises(ValueError):
        session.edit_texts(["un seul"])
    worker.shutdown()


def test_retranscribe_passage_with_precise_model_then_back(app):
    engine, clips = PassageEngine(), []
    session, worker = make_session(app, engine, clips)
    loads = []
    worker.model_loaded.connect(lambda key, _: loads.append(key))
    session.open(list(TIMED), "x", language="fr")
    assert session.retranscribe(Path("a.flac"), 1, 1, "precise")
    assert not session.available and not session.retranscribe(Path("a.flac"), 0, 0)
    wait_until(app, lambda: not session.retranscribing)
    assert clips == [("a.flac", 1.3, 3.2)]
    assert engine.options.language == "fr"
    assert loads == ["turbo"] and engine.model.key == "turbo"  # the passage model is not announced
    assert session.segments[0] is TIMED[0]
    new = session.segments[1]
    assert new.text == "Texte précis." and new.start == pytest.approx(1.5) and new.words[0].start == pytest.approx(1.5)
    worker.shutdown()


def test_retranscribe_failure_reports_and_restores(app):
    engine = PassageEngine()
    worker = ModelWorker(engine, clip_loader=lambda *a: (_ for _ in ()).throw(OSError("fichier absent")))
    session = SessionController(Settings(), worker)
    errors = []
    session.error.connect(lambda message, retry: errors.append(message))
    session.load_model("turbo")
    wait_until(app, lambda: session.model_ready)
    session.open(list(TIMED), "x")
    session.retranscribe(Path("a.flac"), 0, 0)
    wait_until(app, lambda: not session.retranscribing)
    assert "fichier absent" in errors[0] and session.segments == TIMED and engine.model.key == "turbo"
    worker.shutdown()


class NoPreciseEngine(PassageEngine):
    """The passage model cannot be loaded (e.g. missing, offline)."""

    def load(self, spec):
        if spec.key == "precise":
            self.model = None
            raise RuntimeError("modèle absent")
        super().load(spec)


def test_retranscribe_model_failure_reported_once(app):
    engine = NoPreciseEngine()
    worker = ModelWorker(engine, clip_loader=lambda *a: np.zeros(16000))
    session = SessionController(Settings(), worker)
    errors = []
    session.error.connect(lambda message, retry: errors.append((message, retry)))
    session.load_model("turbo")
    wait_until(app, lambda: session.model_ready)
    session.open(list(TIMED), "x")
    session.retranscribe(Path("a.flac"), 0, 0, "precise")
    wait_until(app, lambda: not session.retranscribing and session.model_ready)
    assert len(errors) == 1 and "modèle absent" in errors[0][0] and errors[0][1] is False
    assert engine.model.key == "turbo" and session.segments == TIMED
    worker.shutdown()


# ---- window --------------------------------------------------------------------


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    store = HistoryStore(tmp_path / "history")
    w = MainWindow(Settings(), ModelWorker(PassageEngine(), clip_loader=lambda *a: np.zeros(16000)), CPU.description, history=store)
    wait_until(app, lambda: w.session.model_ready)
    yield w, store
    w.close()


def test_history_entry_with_audio_plays_and_edits_are_saved(app, window, tmp_path):
    w, store = window
    entry_id = store.save(kind="record", title="Enregistrement", segments=list(TIMED), language="fr")
    store.attach_audio(entry_id, np.zeros(3 * SAMPLE_RATE, dtype=np.float32), wait=True)
    w._open_history_entry(entry_id)
    assert w.player.path == store.get(entry_id).audio and w.player.isVisibleTo(w)

    w.edit_button.setChecked(True)
    assert w.transcript.editing and not w.transcript.editor.isReadOnly()
    cursor = w.transcript.editor.textCursor()
    cursor.setPosition(0)
    w.transcript.editor.setTextCursor(cursor)
    w.transcript.editor.insertPlainText("Oui. ")
    w.edit_button.setChecked(False)
    assert w.segments[0].text == "Oui. Bonjour tout le monde."
    assert store.get(entry_id).segments[0].text == "Oui. Bonjour tout le monde."
    assert [e.id for e in store.list("oui")] == [entry_id]

    cursor = w.transcript.editor.textCursor()
    cursor.setPosition(w.transcript.displayed_text().index("mots"))
    w.transcript.editor.setTextCursor(cursor)
    w._retranscribe_selection()
    wait_until(app, lambda: w.session.idle)
    assert [s.text for s in store.get(entry_id).segments] == ["Oui. Bonjour tout le monde.", "Texte précis."]
    assert "Texte précis." in w.transcript.displayed_text()


def test_new_capture_hides_the_player_and_file_is_playable(app, window, tmp_path):
    w, store = window
    audio = tmp_path / "entretien.flac"
    write_audio(audio, np.zeros(SAMPLE_RATE, dtype=np.float32))
    w.session.transcribe_file(audio)
    wait_until(app, lambda: w.session.idle)
    assert w.player.path == audio
    w._clear()
    assert w.player.path is None and not w.player.isVisibleTo(w)


def test_deleting_the_open_entry_releases_and_deletes_its_audio(app, window):
    # Windows cannot delete a file the media player still holds open.
    w, store = window
    entry_id = store.save(kind="record", title="Enregistrement", segments=list(TIMED), language="fr")
    store.attach_audio(entry_id, np.zeros(3 * SAMPLE_RATE, dtype=np.float32), wait=True)
    audio = store.get(entry_id).audio
    w._open_history_entry(entry_id)
    w.player.toggle()
    app.processEvents()
    w.history_panel.delete(entry_id, confirm=False)
    assert w.player.path is None and w.history_id is None
    assert not audio.exists()
