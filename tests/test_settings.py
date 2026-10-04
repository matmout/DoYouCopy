"""Settings window, options built from the settings, and what the engine receives."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mywhisper.config import Settings
from mywhisper.core import model_download
from mywhisper.core.engine import FasterWhisperEngine
from mywhisper.core.models import MODELS
from mywhisper.core.types import Segment, TranscribeOptions
from mywhisper.export.srt import SrtExporter
from mywhisper.gpu import rocm_env
from mywhisper.options import DICTATION, FILE, LIVE, live_config, transcribe_options

# ---- options ------------------------------------------------------------------


def test_options_follow_the_settings():
    settings = Settings(
        language="fr",
        task="translate",
        multilingual=True,
        initial_prompt="  Réunion produit  ",
        beam_size=3,
        condition_previous="off",
        vad_threshold=0.35,
        vad_min_silence_ms=800,
        no_speech_threshold=0.7,
        repetition_penalty=1.1,
        batch_size=8,
        hotwords=["ROCm"],
    )
    options = transcribe_options(settings, FILE)
    assert options.task == "translate" and options.multilingual and options.beam_size == 3
    assert options.initial_prompt == "Réunion produit" and options.hotwords == "ROCm"
    assert options.condition_on_previous_text is False
    assert (options.vad_threshold, options.vad_min_silence_ms) == (0.35, 800)
    assert options.word_timestamps and options.batch_size == 8 and options.hallucination_silence_s == 2.0


def test_options_per_purpose():
    settings = Settings(vad_filter=False, batch_size=16, condition_previous="auto", skip_silence_hallucinations=False)
    live = transcribe_options(settings, LIVE)
    dictation = transcribe_options(settings, DICTATION)
    assert live.batch_size == 0 and not live.word_timestamps
    assert dictation.vad_filter and dictation.batch_size == 0  # dictation always trims silences
    assert live.condition_on_previous_text is None and live.hallucination_silence_s is None
    assert transcribe_options(Settings(initial_prompt="  "), FILE).initial_prompt is None
    config = live_config(Settings(live_step_s=0.5, live_endpoint_s=1.2))
    assert (config.min_step_s, config.endpoint_silence_s) == (0.5, 1.2)


# ---- engine ---------------------------------------------------------------------


class FakeModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return iter([]), type("Info", (), {"language": "fr", "language_probability": 1.0, "duration": 1.0})()


def loaded_engine(tmp_path, key="turbo"):
    engine = FasterWhisperEngine(rocm_env.CPU, tmp_path)
    engine._model = FakeModel()
    engine._spec = MODELS[key]
    return engine


def test_engine_maps_options(tmp_path):
    engine = loaded_engine(tmp_path)
    engine.transcribe("x.wav", TranscribeOptions(language="fr", vad_threshold=0.3, hallucination_silence_s=2.0))
    kwargs = engine._model.kwargs
    assert kwargs["beam_size"] == 1 and kwargs["condition_on_previous_text"] is False  # turbo defaults
    assert kwargs["vad_parameters"] == {"threshold": 0.3, "min_silence_duration_ms": 500}
    assert "hallucination_silence_threshold" not in kwargs  # needs word timestamps

    engine.transcribe(
        "x.wav",
        TranscribeOptions(beam_size=8, condition_on_previous_text=True, word_timestamps=True, hallucination_silence_s=2.0,
                          vad_filter=False),
    )
    kwargs = engine._model.kwargs
    assert kwargs["beam_size"] == 8 and kwargs["condition_on_previous_text"] is True
    assert kwargs["hallucination_silence_threshold"] == 2.0 and kwargs["vad_parameters"] is None


def test_engine_uses_batched_inference_for_files(tmp_path, monkeypatch):
    import faster_whisper

    created = []

    class FakeBatched:
        def __init__(self, model):
            created.append(model)

        def transcribe(self, audio, batch_size, **kwargs):
            self.batch_size = batch_size
            return FakeModel().transcribe(audio, **kwargs)

    monkeypatch.setattr(faster_whisper, "BatchedInferencePipeline", FakeBatched)
    engine = loaded_engine(tmp_path)
    engine.transcribe("x.wav", TranscribeOptions(batch_size=8))
    engine.transcribe("x.wav", TranscribeOptions(batch_size=8))
    assert len(created) == 1  # the pipeline is reused
    engine.transcribe("x.wav", TranscribeOptions(batch_size=8, vad_filter=False))
    assert engine._model.kwargs is not None  # no VAD: back to sequential decoding


def test_engine_configure_unloads_and_sets_threads(tmp_path):
    engine = loaded_engine(tmp_path)
    engine.configure(cpu_threads=3, models_dir=tmp_path / "other")
    assert engine.model is None and engine._threads() == {"cpu_threads": 3}
    assert engine._models_dir == tmp_path / "other"


def test_cpu_device_precision():
    assert rocm_env.detect_device("cpu") is rocm_env.CPU
    assert rocm_env.detect_device("cpu", "float32").compute_type == "float32"
    assert rocm_env.detect_device("cpu", "float16") is rocm_env.CPU  # not a CPU type


# ---- exports and models -----------------------------------------------------------


def test_subtitle_line_length_setting():
    text = "Une phrase de taille moyenne pour un sous-titre court"
    out = SrtExporter().render([Segment(0, 4, text)], max_chars=20, max_lines=1)
    lines = [line for line in out.splitlines() if line and "-->" not in line and not line.isdigit()]
    assert all(len(line) <= 20 for line in lines) and len(lines) >= 3


def test_installed_size_and_discard(tmp_path):
    plain = tmp_path / "small"
    plain.mkdir()
    (plain / "model.bin").write_bytes(b"x" * 1000)
    (plain / model_download.COMPLETE).write_text("repo")
    snapshot = model_download.hf_cache_dir(tmp_path, "large-v3") / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"y" * 500)
    assert model_download.installed_size(tmp_path, "small") == 1000 + len("repo")
    assert model_download.installed_size(tmp_path, "large-v3") == 500
    assert model_download.installed_size(tmp_path, "large-v3-turbo") == 0
    model_download.discard(tmp_path, "large-v3")
    assert model_download.installed_size(tmp_path, "large-v3") == 0


# ---- settings window -----------------------------------------------------------------


@pytest.fixture
def window(tmp_path):
    from test_ui import FakeEngine, app as _app  # noqa: F401

    from PySide6.QtWidgets import QApplication

    from mywhisper.ui.main_window import MainWindow
    from mywhisper.ui.workers import ModelWorker

    QApplication.instance() or QApplication([])
    Settings.save, original = (lambda self, path=None: None), Settings.save
    win = MainWindow(Settings(models_dir=str(tmp_path)), ModelWorker(FakeEngine()), rocm_env.CPU.description)
    yield win
    win.close()
    Settings.save = original


def test_dialog_switches_to_cpu_and_reloads(window):
    from test_ui import wait_until

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    dialog = window.open_settings_dialog("Matériel")
    dialog.device_control.set_value("cpu")
    dialog._device_changed("cpu")
    wait_until(app, lambda: getattr(window.worker._engine, "configured", None) is not None)
    configured = window.worker._engine.configured
    assert configured["device"].device == "cpu" and configured["models_dir"] == Path(window.settings.models_dir)
    assert window.settings.device == "cpu"
    assert dialog.compute_combo.itemData(0) == "auto"
    dialog.close()


def test_dialog_applies_display_language_and_model(window):
    dialog = window.open_settings_dialog()
    dialog.transcript_font_size_spin.setValue(16)
    assert window.transcript.editor.font().pointSize() == 16
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
    assert window.language_combo.currentData() == "en"
    dialog.model_key_combo.setCurrentIndex(dialog.model_key_combo.findData("light"))
    assert window.model_control.value() == "light" and window.settings.model_key == "light"
    dialog.task_combo.setCurrentIndex(dialog.task_combo.findData("translate"))
    assert not dialog.translate_warning.isVisibleTo(dialog)  # "light" can translate
    dialog.close()


def test_dialog_rejects_invalid_hotkey(window):
    from PySide6.QtGui import QKeySequence

    dialog = window.open_settings_dialog("Dictée")
    dialog.hotkey_edit.setKeySequence(QKeySequence("Space"))
    dialog._hotkey_edited()
    assert window.settings.dictation_hotkey == "Ctrl+Shift+Space" and dialog.hotkey_error.text()
    dialog.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+D"))
    dialog._hotkey_edited()
    assert window.settings.dictation_hotkey == "Ctrl+Alt+D"
    dialog.close()


def test_reset_keeps_vocabulary(window):
    window.settings.hotwords = ["ROCm"]
    window.settings.beam_size = 8
    window.settings.theme = "light"
    window.reset_settings()
    assert window.settings.hotwords == ["ROCm"] and window.settings.beam_size == 0
    assert window.settings.theme == Settings().theme


def test_default_export_and_subtitle_settings(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    window.settings.default_export = ".srt"
    window.settings.subtitle_max_chars = 20
    window.session.segments = [Segment(0, 4, "Une phrase de taille moyenne pour un sous-titre court")]
    target = tmp_path / "out.srt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window._export(window.settings.default_export)
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if "-->" not in line]
    assert all(len(line) <= 20 for line in lines)


def test_rocm_cpu_models_are_kept_and_reused(tmp_path, monkeypatch):
    from mywhisper.core import engine as engine_module

    kept = []
    monkeypatch.setattr(engine_module, "_rocm_build", lambda: True)
    monkeypatch.setattr(engine_module, "_keep_forever", kept.append)
    monkeypatch.setattr(engine_module, "_kept_cpu_models", {})
    engine = loaded_engine(tmp_path)
    engine._model_path = "model-dir"
    model = engine._model
    engine.unload()
    assert kept == [model] and engine.model is None
    # loading the same model again on the CPU reuses it instead of creating a new one
    monkeypatch.setattr(engine, "_resolve", lambda spec: "model-dir")
    engine.load(MODELS["turbo"])
    assert engine._model is model
    engine.unload()
    assert kept == [model]  # kept once
