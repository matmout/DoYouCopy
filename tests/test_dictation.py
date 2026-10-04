"""Universal dictation cycle with fakes: no keyboard hook, microphone, clipboard or GPU."""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.types import SAMPLE_RATE, Segment, TranscriptionInfo  # noqa: E402
from mywhisper.dictation.controller import IDLE, RECORDING, TRANSCRIBING, DictationController  # noqa: E402
from mywhisper.gpu.rocm_env import CPU  # noqa: E402
from mywhisper.ui.workers import ModelWorker  # noqa: E402


class FakeEngine:
    device = CPU

    def __init__(self, text="bonjour virgule ça va point d'interrogation", fail=False):
        self.model = object()
        self.text = text
        self.fail = fail
        self.options = []

    def load(self, spec):
        pass

    def unload(self):
        pass

    def transcribe(self, audio, options):
        self.options.append(options)
        if self.fail:
            raise RuntimeError("boom")
        return TranscriptionInfo("fr", 0.99, 1.0), iter([Segment(0, 1, self.text)] if self.text else [])


class FakeRecorder:
    def __init__(self, seconds=1.0, fail=False):
        self.seconds = seconds
        self.fail = fail
        self.is_recording = False
        self.device_name = None
        self.level = 0.5

    def start(self):
        if self.fail:
            raise OSError("pas de micro")
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        return np.zeros(int(self.seconds * SAMPLE_RATE), dtype=np.float32)


class FakePaster:
    def __init__(self):
        self.pasted, self.copied = [], []

    def paste(self, text):
        self.pasted.append(text)

    def copy(self, text):
        self.copied.append(text)


class FakeHook(QObject):
    pressed = Signal()
    released = Signal()
    escape = Signal()

    def __init__(self):
        super().__init__()
        self.armed = False

    def set_escape_armed(self, armed):
        self.armed = armed

    def uninstall(self):
        pass


class FakeOverlay:
    def __init__(self):
        self.calls = []

    def show_listening(self, level_source):
        self.calls.append(("listening", level_source()))

    def show_transcribing(self):
        self.calls.append(("transcribing",))

    def show_message(self, text, error=False):
        self.calls.append(("message", text, error))

    def dismiss(self):
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make(app):
    created = []

    def factory(engine=None, recorder=None, busy=False, own=False, **settings):
        worker = ModelWorker(engine or FakeEngine())
        parts = dict(hook=FakeHook(), overlay=FakeOverlay(), recorder=recorder or FakeRecorder(), paster=FakePaster())
        controller = DictationController(
            Settings(**settings),
            worker,
            is_app_busy=lambda: busy,
            play_sound=lambda samples: parts.setdefault("sounds", []).append(samples),
            foreground_is_own=lambda: own,
            **{k: v for k, v in parts.items() if k != "sounds"},
        )
        created.append(worker)
        return controller, parts

    yield factory
    for worker in created:
        worker.shutdown()


def wait_until(app, predicate, timeout_ms=5000):
    from PySide6.QtCore import QDeadlineTimer

    deadline = QDeadlineTimer(timeout_ms)
    while not predicate():
        assert not deadline.hasExpired(), "timeout"
        app.processEvents()


def test_hold_cycle_pastes_processed_text(app, make):
    controller, parts = make(hotwords=["ROCm"], replacements=[["ça va", "ça roule"]])
    hook = parts["hook"]
    hook.pressed.emit()
    assert controller.state == RECORDING and hook.armed
    assert parts["recorder"].is_recording
    hook.released.emit()
    assert controller.state == TRANSCRIBING
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["paster"].pasted == ["Bonjour, ça roule ? "]
    assert not hook.armed
    assert len(parts["sounds"]) == 2
    assert ("message", "Texte inséré", False) in parts["overlay"].calls
    assert controller.worker._engine.options[0].hotwords == "ROCm"


def test_toggle_mode(app, make):
    controller, parts = make(dictation_mode="toggle", dictation_sounds=False)
    hook = parts["hook"]
    hook.pressed.emit()
    hook.released.emit()
    assert controller.state == RECORDING  # release does not stop in toggle mode
    hook.pressed.emit()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["paster"].pasted and "sounds" not in parts


def test_clipboard_output_and_own_window(app, make):
    controller, parts = make(dictation_output="clipboard")
    controller.on_pressed()
    controller.on_released()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["paster"].copied and not parts["paster"].pasted

    controller, parts = make(own=True)
    controller.on_pressed()
    controller.on_released()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["paster"].copied and not parts["paster"].pasted


def test_voice_commands_can_be_disabled(app, make):
    controller, parts = make(voice_commands=False, dictation_trailing_space=False)
    controller.on_pressed()
    controller.on_released()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["paster"].pasted == ["bonjour virgule ça va point d'interrogation"]


def test_escape_cancels_recording(app, make):
    controller, parts = make()
    controller.on_pressed()
    parts["hook"].escape.emit()
    assert controller.state == IDLE and not parts["recorder"].is_recording
    controller.on_released()  # the release after Esc does nothing
    assert controller.state == IDLE


def test_escape_during_transcription_drops_the_result(app, make):
    controller, parts = make()
    controller.on_pressed()
    controller.on_released()
    controller.cancel()
    assert controller.state == IDLE
    for _ in range(50):
        app.processEvents()
    wait_until(app, lambda: controller.worker._engine.options)
    for _ in range(50):
        app.processEvents()
    assert not parts["paster"].pasted


def test_refused_when_app_busy_or_disabled(app, make):
    controller, parts = make(busy=True)
    controller.on_pressed()
    assert controller.state == IDLE and not parts["recorder"].is_recording
    assert parts["overlay"].calls[-1] == ("message", "MyWhisper est occupé", True)

    controller, parts = make(dictation_enabled=False)
    controller.on_pressed()
    assert controller.state == IDLE


def test_short_recording_and_microphone_failure(app, make):
    controller, parts = make(recorder=FakeRecorder(seconds=0.1))
    controller.on_pressed()
    controller.on_released()
    assert controller.state == IDLE
    assert parts["overlay"].calls[-1][1] == "Trop court"

    controller, parts = make(recorder=FakeRecorder(fail=True))
    controller.on_pressed()
    assert controller.state == IDLE
    assert parts["overlay"].calls[-1][2] is True


def test_silence_and_engine_error(app, make):
    controller, parts = make(engine=FakeEngine(text=""))
    controller.on_pressed()
    controller.on_released()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["overlay"].calls[-1][1] == "Rien entendu" and not parts["paster"].pasted

    controller, parts = make(engine=FakeEngine(fail=True))
    controller.on_pressed()
    controller.on_released()
    wait_until(app, lambda: controller.state == IDLE)
    assert parts["overlay"].calls[-1][2] is True
