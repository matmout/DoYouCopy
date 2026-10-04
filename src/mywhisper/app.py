from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from mywhisper.config import Settings
from mywhisper.core.engine import FasterWhisperEngine

# detect_device() imports ctranslate2, which registers the ROCm DLL directories:
# it must run before PySide6 is imported.
from mywhisper.gpu.rocm_env import detect_device


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    settings = Settings.load()
    device = detect_device(settings.device)
    logging.getLogger(__name__).info("Inference device: %s", device.description)
    engine = FasterWhisperEngine(
        device, Path(settings.models_dir), allow_download=settings.allow_download
    )

    from PySide6.QtWidgets import QApplication

    from mywhisper.ui.main_window import MainWindow
    from mywhisper.ui.workers import ModelWorker

    app = QApplication(sys.argv)
    app.setApplicationName("MyWhisper")
    app.setStyle("windowsvista" if "windowsvista" in _styles() else "Fusion")
    worker = ModelWorker(engine)
    window = MainWindow(settings, worker, device.description)
    window.show()
    return app.exec()


def _styles() -> list[str]:
    from PySide6.QtWidgets import QStyleFactory

    return [s.lower() for s in QStyleFactory.keys()]
