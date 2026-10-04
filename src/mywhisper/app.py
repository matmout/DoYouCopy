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

    from mywhisper.ui import theme
    from mywhisper.ui.main_window import MainWindow
    from mywhisper.ui.workers import ModelWorker

    app = QApplication(sys.argv)
    app.setApplicationName("MyWhisper")
    setup_style(app, settings.theme)
    worker = ModelWorker(engine)
    window = MainWindow(settings, worker, device.description)
    window.setWindowIcon(theme.icon("ph.microphone-fill", window.tokens, "accent"))
    window.show()
    return app.exec()


def setup_style(app, theme_setting: str) -> None:
    """Fusion + the studio stylesheet: identical rendering whatever the Windows version."""
    from mywhisper.ui import theme

    app.setStyle("Fusion")
    theme.load_fonts()
    app.setFont(theme.ui_font())
    theme.apply(app, theme.resolve(theme_setting))
