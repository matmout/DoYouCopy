"""Session controller without any window: capture, transcription and results."""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.types import SAMPLE_RATE  # noqa: E402
from mywhisper.session import SessionController  # noqa: E402
from mywhisper.ui.workers import ModelWorker  # noqa: E402

from test_ui import SEGMENTS, FakeEngine, FakeLive, wait_until  # noqa: E402


class Recorder:
    def __init__(self, seconds: float = 2.0, fail: bool = False) -> None:
        self.is_recording = False
        self.level = 0.0
        self.device_name = None
        self.seconds = seconds
        self.fail = fail

    def start(self):
        if self.fail:
            raise OSError("pas de micro")
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        return np.zeros(int(self.seconds * SAMPLE_RATE), dtype=np.float32)

    def drain(self):
        return np.zeros(160, dtype=np.float32)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make(app):
    workers = []

    def factory(engine=None, recorder=None, **worker_kwargs):
        worker = ModelWorker(engine or FakeEngine(), **worker_kwargs)
        workers.append(worker)
        session = SessionController(Settings(), worker, recorder or Recorder())
        results, errors = [], []
        session.finished.connect(results.append)
        session.error.connect(lambda message, retry: errors.append(message))
        session.load_model("turbo")
        wait_until(app, lambda: session.model_ready)
        return session, results, errors

    yield factory
    for worker in workers:
        worker.shutdown()


def test_file_transcription_result(app, make):
    session, results, _ = make()
    assert session.transcribe_file(Path("C:/audio/entretien.mp3"))
    assert session.busy and not session.available
    assert not session.transcribe_file(Path("autre.wav"))  # one at a time
    wait_until(app, lambda: results)
    result = results[0]
    assert result.kind == "file" and result.name == "entretien"
    assert result.segments == SEGMENTS and result.language == "fr" and result.duration == 3.0
    assert result.source_path == Path("C:/audio/entretien.mp3") and result.audio is None
    assert session.available


def test_recording_keeps_the_audio(app, make):
    session, results, _ = make()
    assert session.start_recording() and session.recording and session.capturing
    session.stop_recording()
    wait_until(app, lambda: results)
    assert results[0].kind == "record" and results[0].audio.size == 2 * SAMPLE_RATE


def test_short_recording_and_microphone_failure(app, make):
    session, results, _ = make(recorder=Recorder(seconds=0.1))
    session.start_recording()
    session.stop_recording()
    assert results == [None] and not session.busy

    session, results, errors = make(recorder=Recorder(fail=True))
    assert not session.start_recording() and not session.start_live()
    assert errors and "pas de micro" in errors[0] and session.available


def test_live_result_merges_sentences(app, make):
    session, results, _ = make(live_factory=FakeLive)
    assert session.start_live() and session.live and not session.available
    wait_until(app, lambda: len(session.segments) == 2)
    session.stop_live()
    assert session.live_stopping
    wait_until(app, lambda: results)
    assert results[0].kind == "live"
    assert [s.text for s in results[0].segments] == ["Bonjour tout le monde.", "Ceci est un test."]
    assert not session.recorder.is_recording and session.available


def test_cancel_and_engine_error(app, make):
    engine = FakeEngine()
    engine.release.clear()
    session, results, _ = make(engine)
    session.transcribe_file(Path("x.wav"))
    session.cancel()
    engine.release.set()
    wait_until(app, lambda: results)
    assert results == [None]

    session, results, errors = make(FakeEngine(fail=True))
    session.transcribe_file(Path("x.wav"))
    wait_until(app, lambda: errors)
    assert "boom" in errors[0] and not session.busy and not results


def test_replacements_apply_to_segments(app, make):
    session, results, _ = make()
    session.settings.replacements = [["segment", "passage"]]
    session.transcribe_file(Path("x.wav"))
    wait_until(app, lambda: results)
    assert [s.text for s in results[0].segments] == ["Premier passage.", "Second passage."]
