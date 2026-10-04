import time

import numpy as np
import pytest

from mywhisper.core.types import SAMPLE_RATE, Segment, Word
from mywhisper.storage.history import HistoryStore, fts_query, segments_from_json, segments_to_json

SEGMENTS = [
    Segment(0.0, 1.5, "Réunion sur ROCm7 et CTranslate2.", (Word(0.0, 0.6, " Réunion"), Word(0.6, 0.9, " sur"))),
    Segment(1.5, 3.0, "Claire présente le budget."),
]


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    yield s
    s.close()


def test_segments_round_trip():
    assert segments_from_json(segments_to_json(SEGMENTS)) == SEGMENTS


def test_fts_query_quotes_and_prefixes():
    assert fts_query('  rocm "budget ') == '"rocm"* "budget"*'
    assert fts_query("   ") == ""


def test_save_list_and_get(store):
    first = store.save(kind="file", title="entretien", segments=SEGMENTS, source="C:/a/entretien.mp3",
                       model="turbo", language="fr", duration=3.0, created=1000.0)
    second = store.save(kind="record", title="dictee", segments=[Segment(0, 1, "Autre chose.")], created=2000.0)
    assert [e.id for e in store.list()] == [second, first]  # newest first
    entry = store.get(first)
    assert entry.segments == SEGMENTS and entry.language == "fr" and entry.duration == 3.0
    assert entry.text == "Réunion sur ROCm7 et CTranslate2.\nClaire présente le budget."
    assert store.get(999) is None and store.count() == 2


def test_full_text_search(store):
    meeting = store.save(kind="file", title="Réunion budget", segments=SEGMENTS)
    store.save(kind="record", title="Courses", segments=[Segment(0, 1, "Acheter du pain.")])
    assert [e.id for e in store.list("presente")] == [meeting]  # accents ignored
    assert [e.id for e in store.list("rocm")] == [meeting]  # prefix: ROCm7
    assert [e.id for e in store.list("claire budget")] == [meeting]  # every word
    assert store.list("claire pain") == []
    assert "«" in store.list("budget")[0].snippet
    store.list('" OR (')  # never raises


def test_autosave_updates_then_edit_rename_favorite(store):
    entry_id = store.save(kind="live", title="direct", segments=SEGMENTS[:1])
    assert store.save(kind="live", title="direct", segments=SEGMENTS, entry_id=entry_id, duration=3.0) == entry_id
    assert store.count() == 1 and store.get(entry_id).segments == SEGMENTS
    store.update_segments(entry_id, [Segment(0, 1, "Texte corrigé.")])
    assert [e.id for e in store.list("corrige")] == [entry_id] and store.list("budget") == []
    store.rename(entry_id, "Point hebdo")
    store.set_favorite(entry_id, True)
    assert [e.title for e in store.list("hebdo", favorites_only=True)] == ["Point hebdo"]
    store.rename(entry_id, "  ")
    assert store.get(entry_id).title == "Sans titre"


def test_audio_kept_purged_and_deleted(store):
    samples = (np.sin(np.arange(SAMPLE_RATE) / 10) * 0.3).astype(np.float32)
    old = store.save(kind="record", title="vieux", segments=SEGMENTS, created=time.time() - 40 * 86400)
    recent = store.save(kind="record", title="récent", segments=SEGMENTS)
    store.attach_audio(old, samples, wait=True)
    store.attach_audio(recent, samples)
    store.wait_for_audio()
    old_audio, recent_audio = store.get(old).audio, store.get(recent).audio
    assert old_audio.suffix == ".flac" and old_audio.stat().st_size > 0 and recent_audio
    assert not list(store.audio_dir.glob("*.part"))

    assert store.purge_audio(30) == 1
    assert store.get(old).audio is None and not old_audio.exists() and store.get(old).text  # text kept
    assert store.purge_audio(0) == 0  # 0 = keep forever

    store.delete(recent)
    assert store.get(recent) is None and not recent_audio.exists()


def test_clear_erases_everything(store):
    entry_id = store.save(kind="record", title="x", segments=SEGMENTS)
    store.attach_audio(entry_id, np.zeros(SAMPLE_RATE, dtype=np.float32), wait=True)
    store.clear()
    assert store.count() == 0 and store.list("réunion") == [] and not list(store.audio_dir.iterdir())


def test_reopen_keeps_the_data(tmp_path):
    store = HistoryStore(tmp_path)
    entry_id = store.save(kind="file", title="persisté", segments=SEGMENTS)
    store.close()
    store = HistoryStore(tmp_path)
    assert store.get(entry_id).segments == SEGMENTS
    store.close()
