from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from mywhisper.config import Settings
from mywhisper.core.engine import FasterWhisperEngine

# detect_device() imports ctranslate2, which registers its DLL directories:
# it must run before PySide6 is imported, and after runtime.startup.prepare().
from mywhisper.gpu.rocm_env import detect_device
from mywhisper.runtime import startup

log = logging.getLogger(__name__)


def main() -> int:
    setup_logging()
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    settings = Settings.load()
    args = sys.argv[1:]

    if "--probe" in args:  # child process of the runtime setup: is the GPU usable?
        startup.prepare("auto")
        startup.write_probe(Path(args[args.index("--probe") + 1]))
        return 0

    choice = startup.prepare(settings.device)
    if "--setup-runtime" in args:  # end of the installer
        return run_runtime_setup(settings)

    device = detect_device(settings.device)
    log.info("Inference device: %s (runtime %s)", device.description, choice.variant)
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
    if not device.is_gpu:
        window.set_cpu_notice(startup.cpu_notice(choice))
    window.install_runtime_requested.connect(lambda: install_runtime_from_app(window))
    tray = setup_dictation(app, window, settings, worker)
    if "--minimized" not in args or tray is None:
        window.show()
    return app.exec()


def setup_logging() -> None:
    """A packaged (windowed) app has no console: log to a file, and give the libraries
    that print progress somewhere harmless to write."""
    from mywhisper.runtime import store

    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if not store.is_frozen():
        logging.basicConfig(level=logging.INFO, format=fmt)
        return
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    log_dir = store.runtime_root().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(log_dir / "mywhisper.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=[handler])


def run_runtime_setup(settings: Settings) -> int:
    """Detects the card and downloads its runtime (called at the end of the installation)."""
    from PySide6.QtWidgets import QApplication

    from mywhisper.runtime import gpu_detect
    from mywhisper.ui import theme
    from mywhisper.ui.runtime_dialog import RuntimeSetupDialog

    app = QApplication(sys.argv)
    app.setApplicationName("MyWhisper")
    setup_style(app, settings.theme)
    detection = gpu_detect.detect()
    log.info("Runtime setup: %s", detection)
    dialog = RuntimeSetupDialog(detection)
    dialog.setWindowIcon(theme.icon("ph.microphone-fill", theme.resolve(settings.theme), "accent"))
    dialog.show()
    dialog.exec()
    return 0


def install_runtime_from_app(window) -> None:
    """From the CPU banner: download, then restart so the new runtime is loaded."""
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QMessageBox

    from mywhisper.runtime import gpu_detect, store
    from mywhisper.ui.runtime_dialog import RuntimeSetupDialog

    dialog = RuntimeSetupDialog(gpu_detect.detect(), window)
    if not dialog.exec() or not dialog.gpu_ready:
        return
    answer = QMessageBox.question(
        window,
        "Redémarrer MyWhisper",
        "L'accélération graphique sera utilisée au prochain démarrage. Redémarrer MyWhisper maintenant ?",
    )
    if answer == QMessageBox.StandardButton.Yes:
        program, arguments = (sys.executable, []) if store.is_frozen() else (sys.executable, ["-m", "mywhisper"])
        window.quit_app()
        QProcess.startDetached(program, arguments)


def setup_dictation(app, window, settings: Settings, worker):
    """Tray icon + system-wide hotkey. Returns None where no tray is available."""
    from PySide6.QtWidgets import QSystemTrayIcon

    from mywhisper.dictation.controller import DictationController
    from mywhisper.dictation.hotkey import KeyboardHook, parse_hotkey
    from mywhisper.ui.tray import TrayIcon
    from mywhisper.ui.widgets.dictation_overlay import DictationOverlay

    log = logging.getLogger(__name__)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning("No system tray: universal dictation disabled")
        return None

    hook = KeyboardHook(app)
    overlay = DictationOverlay(window.tokens)
    controller = DictationController(
        settings,
        worker,
        hook=hook,
        overlay=overlay,
        is_app_busy=lambda: not window.idle or window.recorder.is_recording,
    )
    window.attach_dictation(controller, hook)
    tray = TrayIcon(window.tokens, settings.dictation_hotkey, settings.dictation_enabled, app)

    def open_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def set_enabled(enabled: bool) -> None:
        settings.dictation_enabled = enabled
        window.save_settings()

    tray.open_requested.connect(open_window)
    tray.quit_requested.connect(window.quit_app)
    tray.dictation_toggled.connect(set_enabled)
    controller.state_changed.connect(lambda state: tray.set_listening(state == "recording"))
    window.hotkey_changed.connect(tray.set_hotkey_text)
    window.theme_tokens_changed.connect(lambda t: (overlay.set_tokens(t), tray.set_tokens(t)))
    first_hide = [True]

    def hidden_to_tray() -> None:
        if first_hide[0]:
            first_hide[0] = False
            tray.showMessage(
                "MyWhisper reste disponible",
                f"Dictée : {settings.dictation_hotkey}. Quittez depuis cette icône.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    window.hidden_to_tray.connect(hidden_to_tray)
    window.close_to_tray_available = True
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(tray.hide)
    tray.show()

    try:
        hook.set_hotkey(parse_hotkey(settings.dictation_hotkey))
    except ValueError as exc:
        tray.showMessage("Raccourci de dictée invalide", str(exc), QSystemTrayIcon.MessageIcon.Warning, 6000)
        return tray
    if not hook.install():
        tray.showMessage(
            "Dictée indisponible",
            "Le raccourci global n'a pas pu être installé.",
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )
    return tray


def setup_style(app, theme_setting: str) -> None:
    """Fusion + the studio stylesheet: identical rendering whatever the Windows version."""
    from mywhisper.ui import theme

    app.setStyle("Fusion")
    theme.load_fonts()
    app.setFont(theme.ui_font())
    theme.apply(app, theme.resolve(theme_setting))
