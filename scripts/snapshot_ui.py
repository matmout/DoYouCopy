"""Renders the main window offscreen in every state, dark and light, to PNG files.

Usage : python scripts/snapshot_ui.py [dossier_de_sortie] [--lang fr|en]
No GPU, model or microphone needed: a fake engine and a fake recorder drive the states.
--lang en: the interface and the sample transcript in English (Store listing en-US).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from doyoucopy import i18n
from doyoucopy.app import setup_style
from doyoucopy.config import Settings
from doyoucopy.core.types import Segment, TranscriptionInfo, Word
from doyoucopy.gpu.rocm_env import DeviceConfig
from doyoucopy.ui.main_window import MainWindow
from doyoucopy.ui.widgets.transcript_view import LISTENING_RECORD
from doyoucopy.ui.workers import ModelWorker

GPU = DeviceConfig("cuda", "float16", "GPU · float16")

# Sample transcript per interface language: start, end, sentence; then the live pass
# shown in progress (committed part, provisional part).
SAMPLES = {
    "fr": (
        [
            (0.0, 4.2, "Bonjour à tous, voici une dictée de démonstration."),
            (4.6, 9.8, "Le texte apparaît pendant que je parle, puis il se fige à chaque pause."),
            (10.4, 15.1, "La carte graphique fait tout le travail, sans aucune connexion."),
        ],
        ("Le texte apparaît pendant que je parle,", "puis il se fige à chaque"),
        "modèle absent du cache local.",
    ),
    "en": (
        [
            (0.0, 4.2, "Hello everyone, this is a demonstration dictation."),
            (4.6, 9.8, "The text appears while I speak, then settles at every pause."),
            (10.4, 15.1, "The graphics card does all the work, without any connection."),
        ],
        ("The text appears while I speak,", "then settles at every"),
        "model not in the local cache.",
    ),
}


class FakeEngine:
    device = GPU
    model = None

    def load(self, spec):
        self.model = spec

    def unload(self):
        self.model = None

    def transcribe(self, audio, options):
        return TranscriptionInfo("fr", 0.99, 15.1), iter([])


class FakeRecorder:
    def __init__(self, level=0.0):
        self.is_recording = True
        self.level = level
        self.device_name = None

    def stop(self):
        self.is_recording = False

    def drain(self):
        import numpy as np

        return np.zeros(0, dtype=np.float32)


def words(start: float, text: str) -> Segment:
    parts = text.split(" ")
    ws = tuple(Word(start + i * 0.3, start + i * 0.3 + 0.25, " " + w) for i, w in enumerate(parts))
    return Segment(ws[0].start, ws[-1].end, text, ws)


def settle(app, window) -> None:
    for _ in range(5):
        app.processEvents()
    window.repaint()


def waveform(window) -> None:
    import math

    for i in range(60):
        window.waveform.push(abs(math.sin(i * 0.45)) * (0.35 + 0.5 * abs(math.sin(i * 0.11))))


def main(out: Path, language: str = "fr") -> int:
    i18n.set_language(language)
    tr = i18n.tr
    sentences, (live_done, live_pending), missing = SAMPLES[i18n.language()]
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    i18n.install_qt_translator(app)
    for theme_name in ("dark", "light"):
        settings = Settings(theme=theme_name)
        setup_style(app, theme_name)
        window = MainWindow(settings, ModelWorker(FakeEngine()), GPU.description)
        window.resize(900, 760)
        window.show()
        settle(app, window)

        def shot(name: str) -> None:
            settle(app, window)
            path = out / f"{theme_name}-{name}.png"
            window.grab().save(str(path))
            print(path)

        window._on_model_loading("large-v3-turbo")
        shot("1-chargement")
        window._on_model_loaded("turbo", GPU.description)
        shot("2-vide")

        window.recorder = FakeRecorder()
        window.transcript.show_empty(LISTENING_RECORD)
        window.waveform.set_active(True)
        waveform(window)
        window.timer_label.setText("00:07")
        window._status(tr("Enregistrement…"))
        window._update_controls()
        window.record_button._pulse = 0.35
        window.timer_label.setText("00:07")
        shot("3-enregistrement")

        window.mode_control.set_value("live")
        window.live = True
        window._update_controls()
        window.timer_label.setText("00:12")
        window.record_button._pulse = 0.35
        window.transcript.live_update([words(0.0, sentences[0][2])], "")
        window.transcript._finish_fade()
        window.transcript.live_update([words(4.6, live_done)], live_pending)
        window.transcript._finish_fade()
        window._status(tr("passe {seconds} s").format(seconds=i18n.number(0.38, 2)))
        shot("4-direct")

        window.live = False
        window.recorder.stop()
        window.waveform.set_active(False)
        window.session.segments = [Segment(*s) for s in sentences]
        window.settings_popover.timestamps_check.setChecked(True)
        window._rerender()
        window._update_controls()
        window._status(
            tr("{duration} transcrit en {seconds} s").format(duration="00:15", seconds=i18n.number(1.1))
            + tr(" · {speed}× temps réel").format(speed=14)
        )
        shot("5-termine")

        window.transcript.show_error(
            tr("Impossible de charger {model} : {error}").format(model="large-v3", error=missing), tr("Réessayer")
        )
        shot("6-erreur")

        window.settings_popover.popup_below(window.settings_button)
        settle(app, window)
        window.settings_popover.grab().save(str(out / f"{theme_name}-7-reglages.png"))
        window.settings_popover.hide()
        window.close()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    lang = "fr"
    if "--lang" in args:
        index = args.index("--lang")
        lang = args[index + 1]
        del args[index : index + 2]
    sys.exit(main(Path(args[0] if args else "snapshots"), lang))
