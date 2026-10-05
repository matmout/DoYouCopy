"""Entry point: startup sequence, then the Qt application.

Order matters and is the main thing to check when auditing startup:
1. logging (a packaged app has no console: everything goes to a log file);
2. runtime.startup.prepare(): puts the right CTranslate2 build on sys.path;
3. detect_device(): first import of ctranslate2, before PySide6 loads its DLLs;
4. Qt: QApplication, main window, tray icon and the global dictation hotkey.

Command-line switches: --minimized (start in the tray, used by "start with
Windows"; the Microsoft Store package uses its StartupTask instead), --setup-runtime (end of the installer: GPU runtime download),
--migrate (installer: move the data of MyWhisper, the former name, then exit) and
--probe <file> (child process that reports whether the GPU is usable).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from doyoucopy import __version__, i18n, legacy
from doyoucopy.config import Settings
from doyoucopy.core.engine import FasterWhisperEngine

# detect_device() imports ctranslate2, which registers its DLL directories:
# it must run before PySide6 is imported, and after runtime.startup.prepare().
from doyoucopy.gpu.rocm_env import detect_device
from doyoucopy.i18n import tr
from doyoucopy.runtime import startup

log = logging.getLogger(__name__)


def main() -> int:
    moved = legacy.migrate()  # before logging: the log folder may be one of the moved items
    setup_logging()
    if moved:
        log.info("Data of %s moved: %s", legacy.LEGACY_NAME, ", ".join(moved))
    args = sys.argv[1:]
    if "--migrate" in args:  # the installer, before it uninstalls MyWhisper
        return 0
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    settings = Settings.load()
    i18n.set_language(i18n.resolve(settings.ui_language))
    log.info("Interface language: %s", i18n.language())

    if "--probe" in args:  # child process of the runtime setup: is the GPU usable?
        startup.prepare("auto")
        startup.write_probe(Path(args[args.index("--probe") + 1]))
        return 0

    choice = startup.prepare(settings.device)
    if "--setup-runtime" in args:  # end of the installer
        return run_runtime_setup(settings)

    device = detect_device(settings.device, settings.compute_type)
    log.info("Inference device: %s (runtime %s)", device.description, choice.variant)
    engine = FasterWhisperEngine(
        device, Path(settings.models_dir), allow_download=settings.allow_download
    )
    engine.configure(cpu_threads=settings.cpu_threads)

    from PySide6.QtWidgets import QApplication

    from doyoucopy.ui import app_icon
    from doyoucopy.ui.main_window import MainWindow
    from doyoucopy.ui.workers import ModelWorker

    set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("DoYouCopy")
    i18n.install_qt_translator(app)
    app.setWindowIcon(app_icon.qicon())  # every window, and the taskbar
    setup_style(app, settings.theme)
    worker = ModelWorker(engine)
    window = MainWindow(settings, worker, device.description, history=open_history(settings))
    window.runtime_variant = choice.variant
    if not device.is_gpu:
        window.set_cpu_notice(startup.cpu_notice(choice))
    window.install_runtime_requested.connect(lambda: install_runtime_from_app(window))
    window.restart_requested.connect(lambda: restart_app(window))
    tray = setup_dictation(app, window, settings, worker)
    from doyoucopy.dictation import autostart

    minimized = "--minimized" in args or autostart.launched_at_logon()
    if not minimized or tray is None:
        window.show()
    code = app.exec()
    # Normally already done by MainWindow.closeEvent; covers any other way out.
    if not worker.shutdown():
        # The model thread cannot end (CPU model of the ROCm build of CTranslate2), and
        # a normal exit would wait for it forever. Everything is saved by now (history,
        # settings): end the process without running the native destructors.
        log.info("Exiting with os._exit (model thread pinned)")
        logging.shutdown()
        os._exit(code)
    return code


def set_app_user_model_id() -> None:
    """Gives the process its own taskbar identity: launched with python.exe, Windows would
    otherwise group the window under Python and show the interpreter's icon."""
    if sys.platform != "win32":
        return
    import ctypes

    from doyoucopy.desktop.shortcuts import APP_ID

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        log.warning("Could not set the AppUserModelID")


def open_history(settings: Settings):
    """The history store, with its audio retention applied and leftover audio files
    removed; None if it cannot be opened (the app then runs without history)."""
    from doyoucopy.config import default_history_dir
    from doyoucopy.storage.history import HistoryStore

    try:
        store = HistoryStore(default_history_dir())
        store.purge_audio(settings.history_audio_days)
        store.remove_orphan_audio()
    except Exception:
        log.exception("Could not open the history")
        return None
    return store


def setup_logging() -> None:
    """A packaged (windowed) app has no console: log to a file, and give the libraries
    that print progress somewhere harmless to write."""
    from doyoucopy import diagnostics
    from doyoucopy.runtime import store

    frozen = store.is_frozen()
    if frozen:
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115 (open for the life of the process)
    path = diagnostics.setup_logging(console=not frozen)
    log.info("DoYouCopy %s started, log in %s", __version__, path)


def run_runtime_setup(settings: Settings) -> int:
    """Detects the card and downloads its runtime (called at the end of the installation)."""
    from PySide6.QtWidgets import QApplication

    from doyoucopy.runtime import gpu_detect
    from doyoucopy.ui import app_icon
    from doyoucopy.ui.runtime_dialog import RuntimeSetupDialog

    set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("DoYouCopy")
    i18n.install_qt_translator(app)
    setup_style(app, settings.theme)
    detection = gpu_detect.detect()
    log.info("Runtime setup: %s", detection)
    dialog = RuntimeSetupDialog(detection)
    app.setWindowIcon(app_icon.qicon())
    dialog.show()
    dialog.exec()
    return 0


def install_runtime_from_app(window) -> None:
    """From the CPU banner: download, then restart so the new runtime is loaded."""
    from PySide6.QtWidgets import QMessageBox

    from doyoucopy.runtime import gpu_detect
    from doyoucopy.ui.runtime_dialog import RuntimeSetupDialog

    dialog = RuntimeSetupDialog(gpu_detect.detect(), window)
    if not dialog.exec() or not dialog.gpu_ready:
        return
    answer = QMessageBox.question(
        window,
        tr("Redémarrer DoYouCopy"),
        tr("L'accélération graphique sera utilisée au prochain démarrage. Redémarrer DoYouCopy maintenant ?"),
    )
    if answer == QMessageBox.StandardButton.Yes:
        restart_app(window)


def restart_app(window) -> None:
    """Quits (everything saved, as on a normal exit) and starts a new instance."""
    from PySide6.QtCore import QProcess

    from doyoucopy.runtime import store

    program, arguments = (sys.executable, []) if store.is_frozen() else (sys.executable, ["-m", "doyoucopy"])
    window.quit_app()
    QProcess.startDetached(program, arguments)


def setup_dictation(app, window, settings: Settings, worker):
    """Tray icon + system-wide hotkey. Returns None where no tray is available."""
    from PySide6.QtWidgets import QSystemTrayIcon

    from doyoucopy.dictation.controller import DictationController
    from doyoucopy.dictation.hotkey import KeyboardHook, parse_hotkey
    from doyoucopy.ui.tray import TrayIcon
    from doyoucopy.ui.widgets.dictation_overlay import DictationOverlay

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
        is_app_busy=lambda: not window.session.available,
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
                tr("DoYouCopy reste disponible"),
                tr("Dictée : {hotkey}. Quittez depuis cette icône.").format(hotkey=settings.dictation_hotkey),
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
        tray.showMessage(tr("Raccourci de dictée invalide"), str(exc), QSystemTrayIcon.MessageIcon.Warning, 6000)
        return tray
    if not hook.install():
        tray.showMessage(
            tr("Dictée indisponible"),
            tr("Le raccourci global n'a pas pu être installé."),
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )
    return tray


def setup_style(app, theme_setting: str) -> None:
    """Fusion + the studio stylesheet: identical rendering whatever the Windows version."""
    from doyoucopy.ui import theme

    app.setStyle("Fusion")
    theme.load_fonts()
    app.setFont(theme.ui_font())
    theme.apply(app, theme.resolve(theme_setting))
