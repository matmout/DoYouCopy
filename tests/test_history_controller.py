"""History policy of the main window, without any widget."""

import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mywhisper.config import Settings
from mywhisper.core.types import SAMPLE_RATE, Segment
from mywhisper.history_controller import HistoryController
from mywhisper.session import SessionResult
from mywhisper.storage.history import HistoryStore

from test_ui import wait_until


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    yield s
    s.close()


def result(kind="record", segments=1, audio=None):
    segs = [Segment(i, i + 1.0, f"Phrase {i}.") for i in range(segments)]
    return SessionResult(kind, "dictee", segs, "fr", float(segments), "turbo", audio=audio)


def session(idle=False, segments=1, kind="live"):
    r = result(kind, segments)
    return SimpleNamespace(idle=idle, segments=r.segments, result=lambda: r)


def test_autosave_creates_then_updates_one_entry(app, store):
    ctl = HistoryController(store, Settings())
    current = []
    ctl.current_changed.connect(current.append)
    ctl.autosave(session(segments=2))
    first = ctl.current_id
    ctl.autosave(session(segments=2))  # nothing new: no write
    ctl.autosave(session(segments=3))
    assert store.count() == 1 and ctl.current_id == first and current == [first, first]
    assert len(store.get(first).segments) == 3 and store.get(first).title == "Direct"
    ctl.autosave(session(idle=True, segments=5))  # nothing running: nothing saved
    assert len(store.get(first).segments) == 3
    ctl.new_entry()
    ctl.autosave(session(segments=1))
    assert store.count() == 2 and ctl.current_id != first


def test_record_keeps_audio_only_if_asked(app, store):
    ctl = HistoryController(store, Settings())
    kept = []
    ctl.audio_kept.connect(lambda entry_id, path: kept.append((entry_id, path)))
    ctl.record(result(audio=np.zeros(SAMPLE_RATE, dtype=np.float32)))
    wait_until(app, lambda: kept)
    assert kept[0][0] == ctl.current_id and kept[0][1].is_file()

    ctl.settings.history_keep_audio = False
    ctl.new_entry()
    ctl.record(result(audio=np.zeros(SAMPLE_RATE, dtype=np.float32)))
    assert store.get(ctl.current_id).audio_path is None
    ctl.record(None)  # cancelled or too short
    assert store.count() == 2


def test_dictations_and_disabled_history(app, store):
    ctl = HistoryController(store, Settings())
    ctl.record_dictation("  Première ligne\nseconde  ")
    assert [e.title for e in store.list()] == ["Première ligne"] and ctl.current_id is None
    ctl.settings.history_dictation = False
    ctl.record_dictation("ignorée")
    ctl.settings.history_dictation = True
    ctl.settings.history_enabled = False
    ctl.record_dictation("ignorée aussi")
    ctl.record(result())
    assert store.count() == 1


def test_corrections_forget_and_clear(app, store):
    ctl = HistoryController(store, Settings())
    ctl.record(result())
    entry_id = ctl.current_id
    ctl.save_corrections([Segment(0, 1, "Corrigé.")])
    assert store.get(entry_id).segments[0].text == "Corrigé."
    ctl.forget(entry_id + 1)
    assert ctl.current_id == entry_id
    ctl.forget(entry_id)
    assert ctl.current_id is None
    ctl.clear()
    assert store.count() == 0


def test_without_a_store_everything_is_a_no_op(app):
    ctl = HistoryController(None, Settings())
    ctl.record(result())
    ctl.autosave(session())
    ctl.record_dictation("texte")
    ctl.save_corrections([])
    ctl.clear()
    ctl.purge_audio(30)
    ctl.close()
    assert not ctl.available and not ctl.enabled and ctl.count() is None and ctl.folder is None
