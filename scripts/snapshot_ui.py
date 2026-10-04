"""Renders the main window offscreen in every state, dark and light, to PNG files.

Usage : python scripts/snapshot_ui.py [dossier_de_sortie]
No GPU, model or microphone needed: a fake engine and a fake recorder drive the states.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.app import setup_style  # noqa: E402
from mywhisper.config import Settings  # noqa: E402
from mywhisper.core.types import Segment, TranscriptionInfo, Word  # noqa: E402
from mywhisper.gpu.rocm_env import DeviceConfig  # noqa: E402
from mywhisper.ui.main_window import MainWindow  # noqa: E402
from mywhisper.ui.widgets.transcript_view import LISTENING_RECORD  # noqa: E402
from mywhisper.ui.workers import ModelWorker  # noqa: E402

GPU = DeviceConfig("cuda", "float16", "GPU · float16")

SENTENCES = [
    (0.0, 4.2, "Bonjour à tous, voici une dictée de démonstration."),
    (4.6, 9.8, "Le texte apparaît pendant que je parle, puis il se fige à chaque pause."),
    (10.4, 15.1, "La carte graphique fait tout le travail, sans aucune connexion."),
]


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


def main(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
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
        window._status("Enregistrement…")
        window._update_controls()
        window.record_button._pulse = 0.35
        window.timer_label.setText("00:07")
        shot("3-enregistrement")

        window.mode_control.set_value("live")
        window.live = True
        window._update_controls()
        window.timer_label.setText("00:12")
        window.record_button._pulse = 0.35
        window.transcript.live_update([words(0.0, SENTENCES[0][2])], "")
        window.transcript._finish_fade()
        window.transcript.live_update([words(4.6, "Le texte apparaît pendant que je parle,")], "puis il se fige à chaque")
        window.transcript._finish_fade()
        window._status("passe 0.38 s")
        shot("4-direct")

        window.live = False
        window.recorder.stop()
        window.waveform.set_active(False)
        window.segments = [Segment(*s) for s in SENTENCES]
        window.settings_popover.timestamps_check.setChecked(True)
        window._rerender()
        window._update_controls()
        window._status("00:15 transcrit en 1.1 s · 14× temps réel")
        shot("5-termine")

        window.transcript.show_error(
            "Impossible de charger large-v3 : modèle absent du cache local.", "Réessayer"
        )
        shot("6-erreur")

        window.settings_popover.popup_below(window.settings_button)
        settle(app, window)
        window.settings_popover.grab().save(str(out / f"{theme_name}-7-reglages.png"))
        window.settings_popover.hide()
        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "snapshots")))
