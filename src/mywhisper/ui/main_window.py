from __future__ import annotations

import logging
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mywhisper import export
from mywhisper.audio.recorder import list_input_devices
from mywhisper.config import Settings
from mywhisper.core.models import MODELS
from mywhisper.core.types import Segment
from mywhisper.dictation.hotkey import parse_hotkey
from mywhisper.export.markdown import MarkdownExporter, timecode
from mywhisper.gpu import rocm_env
from mywhisper.runtime import startup
from mywhisper.session import LIVE_KIND, RECORD, SessionController, SessionResult, clock
from mywhisper.storage.history import HistoryStore
from mywhisper.ui import theme
from mywhisper.ui.history_panel import HistoryPanel
from mywhisper.ui.settings_dialog import SettingsDialog
from mywhisper.ui.vocabulary_dialog import VocabularyDialog
from mywhisper.ui.widgets.notice_bar import NoticeBar
from mywhisper.ui.widgets.record_button import RecordButton
from mywhisper.ui.widgets.segmented import SegmentedControl
from mywhisper.ui.widgets.settings_popover import SettingsPopover
from mywhisper.ui.widgets.toast import Toast
from mywhisper.ui.widgets.transcript_view import (
    LISTENING_LIVE,
    LISTENING_RECORD,
    TranscriptView,
)
from mywhisper.ui.widgets.waveform import WaveformView
from mywhisper.ui.workers import ModelWorker

log = logging.getLogger(__name__)

LANGUAGES = [
    (None, "Langue auto"),
    ("fr", "Français"),
    ("en", "Anglais"),
    ("de", "Allemand"),
    ("es", "Espagnol"),
    ("it", "Italien"),
    ("pt", "Portugais"),
    ("nl", "Néerlandais"),
    ("pl", "Polonais"),
    ("ru", "Russe"),
    ("ar", "Arabe"),
    ("zh", "Chinois"),
    ("ja", "Japonais"),
]
MODES = [("record", "Enregistrement"), ("live", "Direct")]
MODEL_LABELS = {"light": "Léger", "turbo": "Turbo", "precise": "Précis"}
ENGINE_SETTINGS = {"device", "compute_type", "cpu_threads", "models_dir", "allow_download"}

AUDIO_FILTER = "Audio / vidéo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4 *.mkv *.webm);;Tous (*)"
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".mp4", ".mkv", ".webm"}
LEVEL_INTERVAL_MS = 33
AUTOSAVE_MS = 30_000  # long sessions are saved as they go: a crash loses 30 s at most
CAPTURE_TITLES = {"record": "Enregistrement", "live": "Direct"}


class MainWindow(QMainWindow):
    hidden_to_tray = Signal()
    hotkey_changed = Signal(str)
    theme_tokens_changed = Signal(object)  # theme.Tokens
    install_runtime_requested = Signal()
    session_finished = Signal(object)  # SessionResult, for the history

    def __init__(
        self,
        settings: Settings,
        worker: ModelWorker,
        device_description: str,
        history: HistoryStore | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.worker = worker
        self.session = SessionController(settings, worker)
        self.history = history
        self.history_id: int | None = None  # history entry of the current result
        self._autosaved_count = 0
        self.tokens = theme.resolve(settings.theme)
        self.record_seconds = 0.0
        # set by app.py when the tray icon and the universal dictation are available
        self.dictation = None
        self.hook = None
        self.close_to_tray_available = False
        self.cpu_notice = None
        self.runtime_variant: str | None = None  # GPU runtime put on the path at startup (app.py)
        self.settings_dialog: SettingsDialog | None = None
        self._quitting = False

        self.setWindowTitle("MyWhisper")
        self.resize(900, 760)
        self.setMinimumSize(720, 600)
        self.setAcceptDrops(True)
        self._build_ui(device_description)
        self._connect_session()
        self._apply_icons()

        self.level_timer = QTimer(self, interval=LEVEL_INTERVAL_MS)
        self.level_timer.timeout.connect(self._update_level)
        self.autosave_timer = QTimer(self, interval=AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self._theme_changed())
        self.session.load_model(self.settings.model_key)

    # ---- construction -------------------------------------------------

    def _build_ui(self, device_description: str) -> None:
        t = self.tokens

        # top bar: wordmark, model, language, settings
        wordmark = QLabel("MyWhisper")
        wordmark.setObjectName("Wordmark")
        self.model_control = SegmentedControl([(k, MODEL_LABELS.get(k, s.label)) for k, s in MODELS.items()])
        self.model_control.set_value(self.settings.model_key)
        self.model_control.setToolTip(
            "Léger : small, pour le processeur.  Turbo : rapide et précis.  Précis : large-v3, plus lent."
        )
        self.model_control.changed.connect(self._model_changed)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES:
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.language)))
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setToolTip("Réglages")
        self.settings_button.clicked.connect(self._open_settings)
        self.history_button = QToolButton()
        self.history_button.setObjectName("IconButton")
        self.history_button.setToolTip("Historique (Ctrl+H)")
        self.history_button.setCheckable(True)
        self.history_button.setVisible(self.history is not None)

        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(56)
        row = QHBoxLayout(top)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        row.addWidget(self.history_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(wordmark)
        row.addStretch()
        for widget in (self.model_control, self.language_combo, self.settings_button):
            row.addWidget(widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        # capture area: mode, record button, waveform + timer, import
        self.mode_control = SegmentedControl(MODES)
        self.mode_control.set_value(self.settings.mode)
        self.record_button = RecordButton(t)
        self.record_button.clicked.connect(self._toggle_capture)
        self.waveform = WaveformView(t)
        self.timer_label = QLabel("00:00")
        self.timer_label.setProperty("mono", True)
        self.timer_label.setFixedWidth(48)
        self.import_button = QPushButton("Importer un fichier")
        self.import_button.setObjectName("LinkButton")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._open_file)
        import_hint = QLabel("ou glissez-le dans la fenêtre")
        import_hint.setProperty("muted", True)

        wave_row = QHBoxLayout()
        wave_row.addStretch()
        wave_row.addSpacing(48 + 12)  # balances the timer so the waveform stays centred
        wave_row.addWidget(self.waveform)
        wave_row.addSpacing(12)
        wave_row.addWidget(self.timer_label)
        wave_row.addStretch()
        import_row = QHBoxLayout()
        import_row.addStretch()
        import_row.addWidget(self.import_button)
        import_row.addWidget(import_hint)
        import_row.addStretch()

        capture = QVBoxLayout()
        capture.setContentsMargins(24, 22, 24, 10)
        capture.setSpacing(6)
        capture.addWidget(self.mode_control, alignment=Qt.AlignmentFlag.AlignHCenter)
        capture.addWidget(self.record_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        capture.addLayout(wave_row)
        capture.addSpacing(4)
        capture.addLayout(import_row)

        # transcript card
        self.transcript = TranscriptView(t)
        self.transcript.retry_requested.connect(self._retry_model)
        self.notice = NoticeBar(t)
        self.notice.action_clicked.connect(self.install_runtime_requested)
        card_row = QVBoxLayout()
        card_row.setContentsMargins(24, 8, 24, 16)
        card_row.setSpacing(10)
        card_row.addWidget(self.notice)
        card_row.addWidget(self.transcript, 1)

        # bottom bar: actions, status, device
        self.copy_button = QToolButton()
        self.copy_button.setText("Copier")
        self.copy_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.copy_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.copy_button.clicked.connect(lambda: self._copy())
        copy_menu = QMenu(self.copy_button)
        copy_menu.addAction("Texte brut", self._copy)
        copy_menu.addAction("Texte horodaté", lambda: self._copy("timestamps"))
        copy_menu.addAction("Markdown", lambda: self._copy("markdown"))
        self.copy_button.setMenu(copy_menu)
        self.export_button = QToolButton()
        self.export_button.setText("Exporter")
        self.export_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.export_button)
        for exporter in export.exporters():
            menu.addAction(f"{exporter.label} ({exporter.suffix})", lambda e=exporter: self._export(e.suffix))
        self.export_button.setMenu(menu)
        self.clear_button = QPushButton("Effacer")
        self.clear_button.clicked.connect(self._clear)
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.setObjectName("OutlineButton")
        self.cancel_button.clicked.connect(lambda: self.session.cancel())
        self.cancel_button.hide()
        self.status_label = QLabel("")
        self.status_label.setProperty("mono", True)
        self.live_chip = QLabel("DIRECT")
        self.live_chip.setObjectName("Chip")
        self.live_chip.setProperty("accent", True)
        self.live_chip.hide()
        self.device_chip = QLabel(device_description)
        self.device_chip.setObjectName("Chip")

        bottom = QFrame()
        bottom.setObjectName("BottomBar")
        bottom.setFixedHeight(52)
        row = QHBoxLayout(bottom)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(4)
        for widget in (self.copy_button, self.export_button, self.clear_button):
            row.addWidget(widget)
        row.addSpacing(8)
        row.addWidget(self.cancel_button)
        row.addStretch()
        row.addWidget(self.status_label)
        row.addSpacing(10)
        row.addWidget(self.live_chip, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.device_chip, alignment=Qt.AlignmentFlag.AlignVCenter)

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        main_column = QVBoxLayout()
        main_column.setSpacing(0)
        main_column.addLayout(capture)
        main_column.addLayout(card_row, 1)
        body = QHBoxLayout()
        body.setSpacing(0)
        self.history_panel: HistoryPanel | None = None
        if self.history is not None:
            panel = HistoryPanel(self.history, t)
            panel.opened.connect(self._open_history_entry)
            panel.deleted.connect(self._history_entry_deleted)
            panel.renamed.connect(self._history_entry_renamed)
            panel.setVisible(self.settings.history_visible)
            self.history_button.setChecked(self.settings.history_visible)
            self.history_button.toggled.connect(self._toggle_history)
            body.addWidget(panel)
            self.history_panel = panel
        body.addLayout(main_column, 1)
        layout.addWidget(top)
        layout.addLayout(body, 1)
        layout.addWidget(bottom)
        self.setCentralWidget(root)

        microphones: list[str] = []
        try:
            microphones = list_input_devices()
        except Exception:
            log.exception("Could not list input devices")
        self.settings_popover = SettingsPopover(self, microphones)
        pop = self.settings_popover
        self._microphones = microphones
        self._sync_popover()
        pop.theme_changed.connect(self._theme_setting_changed)
        pop.timestamps_changed.connect(lambda _: self._rerender())
        pop.vocabulary_requested.connect(self._open_vocabulary)
        pop.all_settings_requested.connect(lambda: self.open_settings_dialog())
        self.transcript.set_font_size(self.settings.transcript_font_size)
        # Settings are the single source of truth, kept current for the universal dictation.
        self.mode_control.changed.connect(lambda v: self._set_setting("mode", v))
        self.language_combo.currentIndexChanged.connect(
            lambda _: self._set_setting("language", self.language_combo.currentData())
        )
        pop.vad_check.toggled.connect(lambda v: self._set_setting("vad_filter", v))
        pop.timestamps_check.toggled.connect(lambda v: self._set_setting("show_timestamps", v))
        pop.mic_combo.currentIndexChanged.connect(
            lambda _: self._set_setting("input_device", pop.mic_combo.currentData())
        )

        self.toast = Toast(root, bottom_offset=52)

        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self._shortcut_capture("record"))
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self._shortcut_capture("live"))
        QShortcut(QKeySequence.StandardKey.Open, self, self._open_file)
        QShortcut(QKeySequence("Ctrl+H"), self, self.history_button.toggle)
        QShortcut(QKeySequence.StandardKey.Save, self, lambda: self._export(self.settings.default_export))
        self.addAction(QAction(self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close))
        self._update_controls()

    def _connect_session(self) -> None:
        s = self.session
        s.changed.connect(self._update_controls)
        s.status.connect(self._status)
        s.error.connect(self._on_error)
        s.capture_started.connect(self._on_capture_started)
        s.capture_stopped.connect(self._stop_meter)
        s.transcription_started.connect(self._on_transcription_started)
        s.segment_added.connect(self._on_segment)
        s.live_updated.connect(self.transcript.live_update)
        s.finished.connect(self._on_finished)
        s.finished.connect(self._record_history)
        s.model_loading.connect(self._on_model_loading)
        s.model_downloading.connect(self._on_model_downloading)
        s.model_loaded.connect(self._on_model_loaded)

    # ---- theme ---------------------------------------------------------

    def _theme_setting_changed(self, setting: str) -> None:
        self._set_setting("theme", setting)
        self._theme_changed()

    # ---- settings ------------------------------------------------------

    def _set_setting(self, name: str, value) -> None:
        setattr(self.settings, name, value)
        self.save_settings()

    def save_settings(self) -> None:
        try:
            self.settings.save()
        except OSError:
            log.exception("Could not save settings")

    # ---- universal dictation --------------------------------------------

    def attach_dictation(self, controller, hook) -> None:
        self.dictation = controller
        self.hook = hook
        controller.dictated.connect(self.record_dictation)

    def _hotkey_edited(self, text: str) -> None:
        if not text:
            return
        try:
            hotkey = parse_hotkey(text)
        except ValueError as exc:
            self.toast.show_message(str(exc))
            return
        self._set_setting("dictation_hotkey", hotkey.text)
        self._apply_hotkey()

    def _apply_hotkey(self) -> None:
        try:
            hotkey = parse_hotkey(self.settings.dictation_hotkey)
        except ValueError:
            return
        if self.hook is not None:
            self.hook.set_hotkey(hotkey)
        self.hotkey_changed.emit(hotkey.text)

    # ---- settings window ------------------------------------------------

    def open_settings_dialog(self, page: str | None = None) -> SettingsDialog:
        dialog = SettingsDialog(
            self.settings,
            self,
            microphones=self._microphones,
            device_description=self.device_chip.text(),
            hardware_status=self._hardware_status,
            hook=self.hook,
            history_dir=self.history.folder if self.history is not None else None,
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.changed.connect(self._on_setting_changed)
        dialog.vocabulary_requested.connect(self._open_vocabulary)
        dialog.install_runtime_requested.connect(self.install_runtime_requested)
        dialog.reset_requested.connect(self.reset_settings)
        dialog.history_clear_requested.connect(self.clear_history)
        self.worker.model_loaded.connect(dialog.set_device_description_from_load)
        if page:
            dialog.show_page(page)
        self.settings_dialog = dialog
        dialog.open()
        return dialog

    def _hardware_status(self) -> tuple[str, bool]:
        notice = self.cpu_notice
        if notice is None:
            if self.settings.device == "cpu":
                return "Calcul sur le processeur, choisi dans ces réglages.", False
            return "Accélération graphique active.", False
        return notice.detail, notice.install_variant is not None

    def _on_setting_changed(self, name: str) -> None:
        self.save_settings()
        value = getattr(self.settings, name)
        if name == "theme":
            self._theme_changed()
        elif name in ("show_timestamps", "replacements"):
            self._rerender()
        elif name == "transcript_font_size":
            self.transcript.set_font_size(value)
        elif name == "language":
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(value)))
            self.language_combo.blockSignals(False)
        elif name == "model_key":
            self.model_control.set_value(value)
            self._model_changed(value)
        elif name in ENGINE_SETTINGS:
            self._apply_engine_settings()
        elif name == "dictation_hotkey":
            self._apply_hotkey()
        elif name == "history_visible":
            self.history_button.setChecked(value)
        elif name == "history_audio_days" and self.history is not None:
            self.history.purge_audio(value)
            self.history_panel.refresh()
        self._sync_popover()

    def _apply_engine_settings(self) -> None:
        """Device, precision, threads or models folder changed: reload the model."""
        device = rocm_env.detect_device(self.settings.device, self.settings.compute_type)
        self.session.reconfigure(
            self.settings.model_key,
            device=device,
            cpu_threads=self.settings.cpu_threads,
            models_dir=Path(self.settings.models_dir),
            allow_download=self.settings.allow_download,
        )
        if device.is_gpu or self.settings.device == "cpu":
            self.set_cpu_notice(None)
        elif self.cpu_notice is None:
            self.set_cpu_notice(startup.cpu_notice(startup.RuntimeChoice(self.runtime_variant)))
        self._status(f"Rechargement du modèle · {device.description}")

    def reset_settings(self) -> None:
        """Back to the defaults, keeping the vocabulary, the models folder and the microphone."""
        kept = {
            name: getattr(self.settings, name)
            for name in ("hotwords", "replacements", "models_dir", "input_device", "mode")
        }
        defaults = Settings(**kept)
        before = {f.name: getattr(self.settings, f.name) for f in fields(Settings)}
        for f in fields(Settings):
            setattr(self.settings, f.name, getattr(defaults, f.name))
        changed = [name for name, value in before.items() if getattr(self.settings, name) != value]
        engine_done = False
        for name in changed:
            if name in ENGINE_SETTINGS:
                if engine_done:
                    continue
                engine_done = True
            self._on_setting_changed(name)
        self.save_settings()
        self.toast.show_message("Réglages par défaut rétablis")

    def _sync_popover(self) -> None:
        pop = self.settings_popover
        for widget in (pop.vad_check, pop.timestamps_check, pop.mic_combo):
            widget.blockSignals(True)
        pop.vad_check.setChecked(self.settings.vad_filter)
        pop.timestamps_check.setChecked(self.settings.show_timestamps)
        pop.mic_combo.setCurrentIndex(max(0, pop.mic_combo.findData(self.settings.input_device)))
        pop.theme_control.set_value(self.settings.theme)
        for widget in (pop.vad_check, pop.timestamps_check, pop.mic_combo):
            widget.blockSignals(False)

    def _open_vocabulary(self) -> None:
        dialog = VocabularyDialog(self.settings, self)
        if dialog.exec():
            self.save_settings()
            self._rerender()

    def _theme_changed(self) -> None:
        self.tokens = theme.resolve(self.settings.theme)
        theme.apply(QApplication.instance(), self.tokens)
        theme.apply_titlebar(self, self.tokens)
        for widget in (self.record_button, self.waveform, self.transcript, self.notice, self.history_panel):
            if widget is not None:
                widget.set_tokens(self.tokens)
        self._apply_icons()
        self._rerender()
        self.theme_tokens_changed.emit(self.tokens)

    def _apply_icons(self) -> None:
        t = self.tokens
        self.settings_button.setIcon(theme.icon("ph.gear-six", t))
        self.settings_button.setIconSize(QSize(20, 20))
        self.history_button.setIcon(theme.icon("ph.clock-counter-clockwise", t))
        self.history_button.setIconSize(QSize(20, 20))
        for button, name in (
            (self.copy_button, "ph.copy"),
            (self.export_button, "ph.export"),
            (self.clear_button, "ph.trash"),
            (self.import_button, "ph.upload-simple"),
        ):
            button.setIcon(theme.icon(name, t))
            button.setIconSize(QSize(17, 17))

    def showEvent(self, event) -> None:
        theme.apply_titlebar(self, self.tokens)
        super().showEvent(event)

    # ---- capture -------------------------------------------------------

    def _shortcut_capture(self, mode: str) -> None:
        if self.session.available:
            self.mode_control.set_value(mode)
        self._toggle_capture()

    def _toggle_capture(self) -> None:
        session = self.session
        dictating = self.dictation is not None and self.dictation.state != "idle"
        if dictating and session.available:
            self._status("Dictée en cours…", 3000)
            return
        if session.live:
            session.stop_live()
        elif session.recording:
            session.stop_recording()
        elif self.mode_control.value() == "live":
            self._start_live()
        else:
            session.start_recording()

    def _start_live(self) -> None:
        if not self.session.start_live():
            return
        message = "Parlez, le texte s'affiche au fil de l'eau."
        if self.cpu_notice is not None:
            message = "Sur le processeur, le texte arrive avec plusieurs secondes de retard."
        elif self.model_control.value() != "turbo":
            message = "Modèle précis : latence plus élevée en direct."
        self._status(message)

    def _on_capture_started(self, kind: str) -> None:
        self.transcript.hide_error()
        if kind == RECORD:
            if not self.segments:
                self.transcript.show_empty(LISTENING_RECORD)
        else:
            self._new_history_entry()
            self.transcript.clear()
            self.transcript.show_empty(LISTENING_LIVE)
        self.record_seconds = 0.0
        self.waveform.set_active(True)
        self.level_timer.start()

    def _stop_meter(self) -> None:
        self.level_timer.stop()
        self.waveform.set_active(False)

    def _update_level(self) -> None:
        self.waveform.push(self.session.recorder.level)
        self.record_seconds += LEVEL_INTERVAL_MS / 1000
        self.timer_label.setText(clock(self.record_seconds))

    # ---- files and transcription ---------------------------------------

    def _open_file(self) -> None:
        if not self.session.available:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Importer un fichier audio", "", AUDIO_FILTER)
        if path:
            self.session.transcribe_file(Path(path))

    def _model_changed(self, key: str) -> None:
        self._set_setting("model_key", key)
        self.session.load_model(key)

    def _retry_model(self) -> None:
        self.session.load_model(self.model_control.value())

    # ---- results -------------------------------------------------------

    @property
    def segments(self) -> list[Segment]:
        return self.session.segments

    def _copy(self, style: str = "plain") -> None:
        if style == "timestamps":
            text = "\n".join(f"[{timecode(s.start)}] {s.text}" for s in self.segments if s.text)
        elif style == "markdown":
            text = MarkdownExporter().render(self.segments)
        else:
            text = "\n".join(s.text for s in self.segments)
        QGuiApplication.clipboard().setText(text)
        self.toast.show_message("Texte copié")

    def _export(self, suffix: str) -> None:
        if not self.segments or not self.idle:
            return
        exporter = next(e for e in export.exporters() if e.suffix == suffix)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la transcription",
            f"{self.session.source_name}{suffix}",
            f"{exporter.label} (*{suffix})",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(suffix)
        try:
            export.export(
                target,
                self.segments,
                max_chars=self.settings.subtitle_max_chars,
                max_lines=self.settings.subtitle_max_lines,
            )
        except Exception as exc:
            self.transcript.show_error(f"Échec de l'export : {exc}")
            return
        self.toast.show_message(f"Exporté vers {target.name}")

    def _clear(self) -> None:
        self.history_id = None
        if self.history_panel is not None:
            self.history_panel.select(None)
        self.session.clear()
        self.transcript.clear()
        self.transcript.show_empty()

    def _rerender(self) -> None:
        if not self.session.live and self.segments:
            self.transcript.render(self.segments, self._timestamps())

    def _timestamps(self) -> bool:
        return self.settings_popover.timestamps_check.isChecked()

    # ---- session callbacks ---------------------------------------------

    def _on_model_loading(self, label: str) -> None:
        if not self.segments and not self.session.busy:
            self.transcript.show_loading(label)

    def _on_model_downloading(self, model_name: str, done: int, total: int) -> None:
        size = f"{done / 1024**3:.1f} / {total / 1024**3:.1f} Go".replace(".", ",")
        if not self.segments and not self.session.busy:
            self.transcript.show_loading_text(f"Premier lancement : téléchargement de {model_name}… {size}")
            self.transcript.set_progress(done / total if total else None)
        self._status(f"Téléchargement du modèle · {done * 100 // max(total, 1)} %")

    def _on_model_loaded(self, key: str, device_description: str) -> None:
        if not self.session.busy:
            self.transcript.set_progress(None)
        self.device_chip.setText(device_description)
        if not self.segments and not self.session.busy:
            self.transcript.show_empty()
        self._status(f"Modèle {MODELS[key].model_name} prêt.", 4000)

    def _on_transcription_started(self) -> None:
        self._new_history_entry()
        self.transcript.clear()
        self.transcript.hide_error()
        self.transcript.set_progress(0.0)

    def _on_segment(self, segment: Segment, progress: float | None) -> None:
        self.transcript.append_segment(segment, self._timestamps())
        if progress is not None:
            self.transcript.set_progress(progress)

    def _on_finished(self, result: SessionResult | None) -> None:
        self.transcript.set_progress(None)
        if result is not None and result.kind == LIVE_KIND:
            self.transcript.render(self.segments, self._timestamps())
        elif not self.segments:
            self.transcript.show_empty()
        if result is not None:
            self.session_finished.emit(result)

    # ---- history ---------------------------------------------------------

    def _new_history_entry(self) -> None:
        self.history_id = None
        self._autosaved_count = 0
        if self.history_panel is not None:
            self.history_panel.select(None)

    def _history_on(self) -> bool:
        return self.history is not None and self.settings.history_enabled

    def _save_history(self, result: SessionResult) -> None:
        title = result.name if result.kind == "file" else CAPTURE_TITLES.get(result.kind, result.name)
        try:
            self.history_id = self.history.save(
                kind=result.kind,
                title=title,
                segments=result.segments,
                entry_id=self.history_id,
                source=str(result.source_path or ""),
                model=result.model_key,
                language=result.language,
                duration=result.duration,
            )
        except Exception:
            log.exception("Could not save the history")
            return
        self._autosaved_count = len(result.segments)
        self.history_panel.current_id = self.history_id
        self.history_panel.refresh()

    def _autosave(self) -> None:
        session = self.session
        if session.idle or not self._history_on() or len(session.segments) == self._autosaved_count:
            return
        self._save_history(session.result())

    def _record_history(self, result: SessionResult | None) -> None:
        if result is None or not self._history_on():
            return
        self._save_history(result)
        if self.history_id is not None and result.audio is not None and self.settings.history_keep_audio:
            try:
                self.history.attach_audio(self.history_id, result.audio)
            except Exception:
                log.exception("Could not keep the audio")
            self.history_panel.refresh()

    def record_dictation(self, text: str) -> None:
        """Universal dictation: kept only if asked (text only, never the audio)."""
        text = text.strip()
        if not (self._history_on() and self.settings.history_dictation and text):
            return
        try:
            self.history.save(
                kind="dictation",
                title=text.splitlines()[0][:60],
                segments=[Segment(0.0, 0.0, text)],
                model=self.settings.model_key,
            )
        except Exception:
            log.exception("Could not save the dictation")
            return
        self.history_panel.refresh()

    def _open_history_entry(self, entry_id: int) -> None:
        entry = self.history.get(entry_id)
        if entry is None:
            return
        if not self.session.open(entry.segments, entry.title):
            self.toast.show_message("Terminez d'abord la transcription en cours")
            self.history_panel.select(self.history_id)
            return
        self.history_id = entry_id
        self.history_panel.select(entry_id)
        self.transcript.hide_error()
        if entry.segments:
            self.transcript.render(entry.segments, self._timestamps())
        else:
            self.transcript.show_empty()
        self._status(f"{entry.title} · {entry.date_label()}", 6000)

    def _history_entry_deleted(self, entry_id: int) -> None:
        if entry_id == self.history_id:
            self.history_id = None

    def _history_entry_renamed(self, entry_id: int, title: str) -> None:
        if entry_id == self.history_id:
            self.session.source_name = title

    def _toggle_history(self, visible: bool) -> None:
        if self.history_panel is None:
            return
        self.history_panel.setVisible(visible)
        if visible:
            self.history_panel.search.setFocus()
        self._set_setting("history_visible", visible)

    def clear_history(self) -> None:
        if self.history is None:
            return
        self.history.clear()
        self.history_id = None
        self.history_panel.refresh()
        self.toast.show_message("Historique effacé")

    # ---- CPU fallback ----------------------------------------------------

    def set_cpu_notice(self, notice) -> None:
        """notice: runtime.startup.CpuNotice, or None when the GPU is used."""
        self.cpu_notice = notice
        if notice is None:
            self.notice.hide()
            return
        action = "Installer l'accélération" if notice.install_variant else None
        self.notice.show_notice(notice.title, notice.detail, action)

    def _on_error(self, message: str, failed_load: bool) -> None:
        self.transcript.set_progress(None)
        if not self.segments:
            self.transcript.show_empty()
        self.transcript.show_error(message, "Réessayer" if failed_load else None)

    # ---- helpers ------------------------------------------------------

    @property
    def idle(self) -> bool:
        return self.session.idle

    def status_text(self) -> str:
        return self.status_label.text()

    def _status(self, text: str, timeout_ms: int = 0) -> None:
        self.status_label.setText(text)
        if timeout_ms:
            QTimer.singleShot(timeout_ms, lambda: self.status_label.text() == text and self.status_label.setText(""))

    def _update_controls(self) -> None:
        s = self.session
        capturing = s.capturing
        self.record_button.set_loading(s.model_loading_now and not capturing)
        self.record_button.set_active(capturing)
        if capturing:
            self.record_button.setEnabled(not s.live_stopping)  # stays clickable to stop
        else:
            self.record_button.setEnabled(not s.model_loading_now and not s.busy)
        self.mode_control.setEnabled(s.available)
        self.model_control.setEnabled(s.available)
        self.language_combo.setEnabled(not capturing)
        self.import_button.setEnabled(s.available)
        self.cancel_button.setVisible(s.busy)
        self.live_chip.setVisible(s.live)
        if not capturing:
            self.timer_label.setText("00:00")
        has_text = bool(self.segments)
        self.copy_button.setEnabled(has_text)
        self.export_button.setEnabled(has_text and self.idle)
        self.clear_button.setEnabled(has_text and self.idle)

    # ---- Qt events ----------------------------------------------------

    def _audio_url(self, event) -> Path | None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in AUDIO_SUFFIXES:
            return Path(urls[0].toLocalFile())
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._audio_url(event) and self.session.available:
            event.acceptProposedAction()
            self.transcript.set_drag_active(True)

    def dragLeaveEvent(self, event) -> None:
        self.transcript.set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self.transcript.set_drag_active(False)
        path = self._audio_url(event)
        if path:
            self.session.transcribe_file(path)

    def _open_settings(self) -> None:
        self._sync_popover()
        self.settings_popover.popup_below(self.settings_button)

    def quit_app(self) -> None:
        self._quitting = True
        self.close()

    def closeEvent(self, event) -> None:
        if self.close_to_tray_available and self.settings.close_to_tray and not self._quitting:
            event.ignore()
            self.hide()
            self.save_settings()
            self.hidden_to_tray.emit()
            return
        self.session.shutdown()
        self._autosave()
        if self.history is not None:
            self.history.close()
        self.save_settings()
        self.worker.shutdown()
        super().closeEvent(event)
        if self.close_to_tray_available:  # the tray keeps the app alive otherwise
            QApplication.quit()
