"""Headless UI test with a fake engine: no GPU, no model, no microphone needed."""

import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.types import Segment, TranscriptionInfo  # noqa: E402
from mywhisper.gpu.rocm_env import CPU  # noqa: E402
from mywhisper.ui.main_window import MainWindow  # noqa: E402
from mywhisper.ui.workers import ModelWorker  # noqa: E402

SEGMENTS = [Segment(0, 1.5, "Premier segment."), Segment(1.5, 3, "Second segment.")]


class FakeEngine:
    def __init__(self, fail: bool = False) -> None:
        self.device = CPU
        self.model = None
        self.fail = fail
        self.release = threading.Event()
        self.release.set()

    def load(self, spec):
        self.model = spec

    def unload(self):
        self.model = None

    def transcribe(self, audio, options):
        if self.fail:
            raise RuntimeError("boom")

        def gen():
            for s in SEGMENTS:
                self.release.wait(5)
                yield s

        return TranscriptionInfo("fr", 0.99, 3.0), gen()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    windows = []

    def factory(engine):
        window = MainWindow(Settings(), ModelWorker(engine), CPU.description)
        windows.append(window)
        return window

    yield factory
    for window in windows:
        window.close()


def wait_until(app, predicate, timeout_ms=5000):
    from PySide6.QtCore import QDeadlineTimer

    deadline = QDeadlineTimer(timeout_ms)
    while not predicate():
        assert not deadline.hasExpired(), "timeout"
        app.processEvents()


def test_progressive_transcription(app, make_window):
    window = make_window(FakeEngine())
    wait_until(app, lambda: window.model_ready)
    window._start_transcription(Path("x.wav"))
    assert window.busy and window.cancel_button.isVisibleTo(window)
    wait_until(app, lambda: not window.busy)
    assert window.segments == SEGMENTS
    assert window.text.toPlainText() == "Premier segment.\nSecond segment."
    assert window.export_button.isEnabled()
    window.timestamps_check.setChecked(True)
    assert window.text.toPlainText().startswith("[00:00 → 00:01]  Premier")


def test_cancel_stops_after_current_segment(app, make_window):
    engine = FakeEngine()
    engine.release.clear()
    window = make_window(engine)
    wait_until(app, lambda: window.model_ready)
    window._start_transcription(Path("x.wav"))
    window.worker.cancel()
    engine.release.set()
    wait_until(app, lambda: not window.busy)
    assert len(window.segments) <= 1
    assert "annulée" in window.statusBar().currentMessage()


def test_error_resets_ui(app, make_window, monkeypatch):
    shown = []
    monkeypatch.setattr("mywhisper.ui.main_window.QMessageBox.warning", lambda *a: shown.append(a[2]))
    window = make_window(FakeEngine(fail=True))
    window._start_transcription(Path("x.wav"))
    wait_until(app, lambda: not window.busy)
    assert shown and "boom" in shown[0]
    assert window.record_button.isEnabled()
