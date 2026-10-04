"""Headless UI test with a fake engine: no GPU, no model, no microphone needed."""

import os
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.live import LiveUpdate  # noqa: E402
from mywhisper.core.types import Segment, TranscriptionInfo, Word  # noqa: E402
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

    def configure(self, **kwargs):
        self.configured = kwargs
        self.unload()

    def transcribe(self, audio, options):
        if self.fail:
            raise RuntimeError("boom")

        def gen():
            for s in SEGMENTS:
                self.release.wait(5)
                yield s

        return TranscriptionInfo("fr", 0.99, 3.0), gen()


class FailingLoadEngine(FakeEngine):
    """The first model load fails (e.g. model missing offline), the retry succeeds."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def load(self, spec):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("cache vide")
        super().load(spec)


class FakeRecorder:
    def __init__(self) -> None:
        self.is_recording = False
        self.level = 0.0
        self.device_name = None

    def start(self):
        self.is_recording = True

    def stop(self):
        self.is_recording = False

    def drain(self):
        import numpy as np

        return np.zeros(160, dtype=np.float32)


def words_segment(*words: tuple[float, str]) -> Segment:
    ws = tuple(Word(start, start + 0.2, text) for start, text in words)
    return Segment(ws[0].start, ws[-1].end, "".join(w.text for w in ws).strip(), ws)


class FakeLive:
    """Plays scripted updates, one per step, then flushes the last one."""

    UPDATES = [
        LiveUpdate([], "Bonjour tout"),
        LiveUpdate([words_segment((0.0, " Bonjour"), (0.4, " tout"))], "le monde"),
        LiveUpdate([words_segment((0.8, " le"), (1.0, " monde."))], "Ceci est"),
    ]
    FLUSH = LiveUpdate([words_segment((1.5, " Ceci"), (1.8, " est"), (2.0, " un"), (2.2, " test."))])

    def __init__(self, engine, options, config=None) -> None:
        self.updates = list(self.UPDATES)

    def feed(self, samples):
        pass

    def ready(self):
        return bool(self.updates)

    def step(self):
        return self.updates.pop(0)

    def flush(self):
        return self.FLUSH


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    windows = []

    def factory(engine, **worker_kwargs):
        window = MainWindow(Settings(), ModelWorker(engine, **worker_kwargs), CPU.description)
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
    wait_until(app, lambda: window.session.model_ready)
    window.session.transcribe_file(Path("x.wav"))
    assert window.session.busy and window.cancel_button.isVisibleTo(window)
    wait_until(app, lambda: not window.session.busy)
    assert window.segments == SEGMENTS
    assert window.transcript.displayed_text() == "Premier segment.\nSecond segment."
    assert window.export_button.isEnabled()
    assert not window.transcript.progress.isVisibleTo(window)
    window.settings_popover.timestamps_check.setChecked(True)
    assert window.transcript.displayed_text().startswith("00:00   Premier")


def test_cancel_stops_after_current_segment(app, make_window):
    engine = FakeEngine()
    engine.release.clear()
    window = make_window(engine)
    wait_until(app, lambda: window.session.model_ready)
    window.session.transcribe_file(Path("x.wav"))
    window.worker.cancel()
    engine.release.set()
    wait_until(app, lambda: not window.session.busy)
    assert len(window.segments) <= 1
    assert "annulée" in window.status_text()


def test_error_shows_inline_banner(app, make_window):
    window = make_window(FakeEngine(fail=True))
    wait_until(app, lambda: window.session.model_ready)
    window.session.transcribe_file(Path("x.wav"))
    wait_until(app, lambda: not window.session.busy)
    banner = window.transcript.banner
    assert banner.isVisibleTo(window) and "boom" in banner.message.text()
    assert not banner.action_button.isVisibleTo(window)  # nothing to retry
    assert window.record_button.isEnabled()


def test_model_load_failure_offers_retry(app, make_window):
    engine = FailingLoadEngine()
    window = make_window(engine)
    banner = window.transcript.banner
    wait_until(app, lambda: banner.isVisibleTo(window))
    assert "cache vide" in banner.message.text() and banner.action_button.isVisibleTo(window)
    banner.action_button.click()
    wait_until(app, lambda: window.session.model_ready)
    assert engine.attempts == 2 and not banner.isVisibleTo(window)


def test_live_mode(app, make_window):
    window = make_window(FakeEngine(), live_factory=FakeLive)
    window.session.recorder = FakeRecorder()
    wait_until(app, lambda: window.session.model_ready)

    window._start_live()
    assert window.session.live and window.record_button.active and window.record_button.isEnabled()
    assert not window.import_button.isEnabled() and not window.mode_control.isEnabled()
    assert window.live_chip.isVisibleTo(window)
    wait_until(app, lambda: len(window.segments) == 2)
    wait_until(app, lambda: window.transcript.displayed_text() == "Bonjour tout le monde.\nCeci est")

    window.session.stop_live()  # stop: final pass, then controls come back
    wait_until(app, lambda: not window.session.live)
    assert [s.text for s in window.segments] == ["Bonjour tout le monde.", "Ceci est un test."]
    assert window.transcript.displayed_text() == "Bonjour tout le monde.\nCeci est un test."
    assert not window.session.recorder.is_recording and not window.record_button.active
    assert window.record_button.isEnabled() and window.mode_control.isEnabled()
    assert window.export_button.isEnabled() and not window.live_chip.isVisibleTo(window)


def test_shortcut_selects_mode_then_captures(app, make_window):
    window = make_window(FakeEngine(), live_factory=FakeLive)
    window.session.recorder = FakeRecorder()
    wait_until(app, lambda: window.session.model_ready)
    window._shortcut_capture("live")
    assert window.mode_control.value() == "live" and window.session.live
    window._shortcut_capture("record")  # while live: stops the session, mode unchanged
    wait_until(app, lambda: not window.session.live)
    assert window.mode_control.value() == "live"


def test_copy_as_timestamps_and_markdown(app, make_window):
    window = make_window(FakeEngine())
    window.session.segments = list(SEGMENTS)
    window._copy("timestamps")
    assert app.clipboard().text() == "[00:00] Premier segment.\n[00:01] Second segment."
    window._copy("markdown")
    assert app.clipboard().text().startswith("*[00:00]* Premier segment.")
    window._copy()
    assert app.clipboard().text() == "Premier segment.\nSecond segment."


def test_replacements_and_hotwords_apply_to_transcription(app, make_window):
    engine = FakeEngine()
    seen = []
    transcribe = engine.transcribe
    engine.transcribe = lambda audio, options: (seen.append(options), transcribe(audio, options))[1]
    window = make_window(engine)
    window.settings.replacements = [["segment", "passage"]]
    window.settings.hotwords = ["ROCm", "Radeon"]
    wait_until(app, lambda: window.session.model_ready)
    window.session.transcribe_file(Path("x.wav"))
    wait_until(app, lambda: window.idle)
    assert [s.text for s in window.segments] == ["Premier passage.", "Second passage."]
    assert seen[0].hotwords == "ROCm, Radeon" and seen[0].word_timestamps


def test_widgets_keep_settings_current(app, make_window):
    window = make_window(FakeEngine())
    window.language_combo.setCurrentIndex(window.language_combo.findData("en"))
    window.settings_popover.vad_check.setChecked(False)
    assert window.settings.language == "en" and window.settings.vad_filter is False


def test_vocabulary_dialog_writes_settings(app):
    from mywhisper.ui.vocabulary_dialog import VocabularyDialog

    settings = Settings(replacements=[["a", "b"]])
    dialog = VocabularyDialog(settings)
    dialog.hotwords_edit.setPlainText("ROCm\n\n  Radeon ")
    dialog._add_row("rock m", "ROCm")
    dialog._add_row("   ", "ignoré")
    dialog.voice_check.setChecked(False)
    dialog.accept()
    assert settings.hotwords == ["ROCm", "Radeon"]
    assert settings.replacements == [["a", "b"], ["rock m", "ROCm"]]
    assert settings.voice_commands is False


def test_close_hides_to_tray_until_quit(app, make_window, monkeypatch):
    from PySide6.QtWidgets import QApplication as QApp

    quits = []
    monkeypatch.setattr(QApp, "quit", lambda: quits.append(True))
    window = make_window(FakeEngine())
    window.close_to_tray_available = True
    hidden = []
    window.hidden_to_tray.connect(lambda: hidden.append(True))
    window.show()
    window.close()
    assert hidden and not window.isVisible() and not quits
    window.quit_app()
    assert quits


def test_invalid_hotkey_is_reverted(app, make_window):
    window = make_window(FakeEngine())
    window._hotkey_edited("Space")
    assert window.settings.dictation_hotkey == "Ctrl+Shift+Space"
    window._hotkey_edited("Ctrl+Alt+D")
    assert window.settings.dictation_hotkey == "Ctrl+Alt+D"


def test_cpu_notice_banner_and_install_action(app, make_window):
    from mywhisper.runtime.startup import CpuNotice

    window = make_window(FakeEngine())
    requested = []
    window.install_runtime_requested.connect(lambda: requested.append(True))
    window.set_cpu_notice(CpuNotice("Transcription plus lente sur cette machine", "Carte NVIDIA détectée", "nvidia"))
    assert window.notice.isVisibleTo(window) and window.notice.action.isVisibleTo(window)
    window.notice.action.click()
    assert requested
    window.set_cpu_notice(CpuNotice("Transcription plus lente sur cette machine", "Intel UHD"))
    assert not window.notice.action.isVisibleTo(window)
    window.set_cpu_notice(None)
    assert not window.notice.isVisibleTo(window)


def test_model_download_progress_is_shown(app, make_window):
    window = make_window(FakeEngine())
    window._on_model_downloading("large-v3-turbo", 800 * 1024**2, 1600 * 1024**2)
    assert "téléchargement de large-v3-turbo" in window.transcript.skeleton.label.text()
    assert window.transcript.progress.isVisibleTo(window)
    assert "50 %" in window.status_text()


def test_runtime_dialog_install_flow(app, monkeypatch):
    from mywhisper.runtime import install
    from mywhisper.runtime.gpu_detect import Adapter, Detection
    from mywhisper.ui import runtime_dialog

    monkeypatch.setattr(runtime_dialog.store, "is_installed", lambda package: False)
    removed = []
    monkeypatch.setattr(runtime_dialog.store, "remove", lambda package: removed.append(package))

    def fake_install(package, progress=None, cancel=None):
        progress("download", 1, 2)
        progress("extract", 2, 2)

    monkeypatch.setattr(install, "install", fake_install)
    detection = Detection("nvidia", Adapter("NVIDIA GeForce RTX 4070", "nvidia"), "Carte NVIDIA détectée : RTX 4070")

    ok = runtime_dialog.RuntimeSetupDialog(detection, probe=lambda: {"ok": True})
    wait_until(app, lambda: ok._thread is None and ok.cancel_button.text() == "Terminer")
    assert ok.gpu_ready and "activée" in ok.title.text()

    bad = runtime_dialog.RuntimeSetupDialog(detection, probe=lambda: {"ok": False})
    wait_until(app, lambda: bad._thread is None and bad.cancel_button.text() == "Terminer")
    assert not bad.gpu_ready and "pilote NVIDIA" in bad.detail.text() and removed

    cpu = runtime_dialog.RuntimeSetupDialog(Detection("cpu", None, "Aucune carte graphique compatible détectée"))
    assert cpu.package is None and "processeur" in cpu.detail.text()


# ---- history ------------------------------------------------------------------


@pytest.fixture
def history_window(app, tmp_path, monkeypatch):
    from mywhisper.storage.history import HistoryStore

    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    store = HistoryStore(tmp_path / "history")
    windows = []

    def factory(engine=None, **worker_kwargs):
        window = MainWindow(
            Settings(history_visible=True), ModelWorker(engine or FakeEngine(), **worker_kwargs), CPU.description, history=store
        )
        windows.append(window)
        wait_until(app, lambda: window.session.model_ready)
        return window

    yield factory, store
    for window in windows:
        window.close()


def test_finished_transcription_is_kept_and_reopened(app, history_window):
    make, store = history_window
    window = make()
    window.session.transcribe_file(Path("C:/audio/entretien.mp3"))
    wait_until(app, lambda: window.session.idle)
    entries = store.list()
    assert [e.title for e in entries] == ["entretien"] and window.history_id == entries[0].id
    assert window.history_panel.list.count() == 1
    assert "entretien" in window.history_panel.list.item(0).text()

    window._clear()
    assert window.segments == [] and window.history_id is None
    window.history_panel.opened.emit(entries[0].id)
    assert [s.text for s in window.segments] == ["Premier segment.", "Second segment."]
    assert window.transcript.displayed_text() == "Premier segment.\nSecond segment."
    assert window.session.source_name == "entretien" and window.history_id == entries[0].id

    window.history_panel.search.setText("second")
    window.history_panel.refresh()
    assert window.history_panel.list.count() == 1 and "«Second»" in window.history_panel.list.item(0).text()
    window.history_panel.search.setText("absent")
    window.history_panel.refresh()
    assert window.history_panel.list.count() == 0 and window.history_panel.empty.isVisibleTo(window)


def test_live_session_autosaves_then_keeps_audio(app, history_window):
    make, store = history_window
    window = make(live_factory=FakeLive)
    window.session.recorder = FakeRecorder()
    window._start_live()
    wait_until(app, lambda: len(window.segments) == 2)
    window._autosave()  # what the timer does during a long session
    draft = store.list()
    assert len(draft) == 1 and draft[0].kind == "live"
    window.session.stop_live()
    wait_until(app, lambda: not window.session.live)
    store.wait_for_audio()
    entries = store.list()
    assert len(entries) == 1 and entries[0].id == draft[0].id  # same entry, completed
    entry = store.get(entries[0].id)
    assert [s.text for s in entry.segments] == ["Bonjour tout le monde.", "Ceci est un test."]
    assert entry.audio is not None


def test_history_options(app, history_window):
    make, store = history_window
    window = make()
    window.settings.history_keep_audio = False
    window.session.recorder = FakeRecorder()
    window.record_dictation("Texte dicté\nsur deux lignes")
    assert [e.title for e in store.list()] == ["Texte dicté"]  # dictations are kept by default
    window.settings.history_dictation = False
    window.record_dictation("Autre dictée")
    assert store.count() == 1

    window.settings.history_enabled = False
    window.session.transcribe_file(Path("x.wav"))
    wait_until(app, lambda: window.session.idle)
    assert store.count() == 1

    window.clear_history()
    assert store.count() == 0 and window.history_panel.list.count() == 0


def test_history_toggle_and_busy_session(app, history_window):
    engine = FakeEngine()
    make, store = history_window
    window = make(engine)
    entry_id = store.save(kind="file", title="ancien", segments=SEGMENTS)
    window.history_panel.refresh()
    window.show()
    assert window.history_panel.isVisible()
    window.history_button.click()
    assert not window.history_panel.isVisible() and window.settings.history_visible is False

    engine.release.clear()
    window.session.transcribe_file(Path("x.wav"))
    window._open_history_entry(entry_id)  # refused while a transcription runs
    assert window.history_id != entry_id
    engine.release.set()
    wait_until(app, lambda: window.session.idle)


def test_audio_source_setting_and_consent_reminder(app, make_window):
    window = make_window(FakeEngine())
    shown = []
    window.toast.show_message = shown.append
    window._source_changed("both")
    assert window.settings.audio_source == "both"
    assert shown and "participants" in shown[0]
    window._source_changed("system")
    assert len(shown) == 1  # once per run
    window.session.recorder = FakeRecorder()
    wait_until(app, lambda: window.session.model_ready)
    window._start_live()
    assert not window.source_control.isEnabled()
    window.session.stop_live()
