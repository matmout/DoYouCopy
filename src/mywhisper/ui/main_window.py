from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
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
from mywhisper.audio.recorder import MicRecorder, list_input_devices
from mywhisper.config import Settings
from mywhisper.core.live import LiveUpdate, merge_sentences
from mywhisper.core.models import MODELS
from mywhisper.core.types import SAMPLE_RATE, AudioSource, Segment, TranscribeOptions
from mywhisper.ui import theme
from mywhisper.ui.widgets.record_button import RecordButton
from mywhisper.ui.widgets.segmented import SegmentedControl
from mywhisper.ui.widgets.settings_popover import SettingsPopover
from mywhisper.ui.widgets.toast import Toast
from mywhisper.ui.widgets.transcript_view import (
    LISTENING_LIVE,
    LISTENING_RECORD,
    TranscriptView,
    clock,
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
MODEL_LABELS = {"turbo": "Turbo", "precise": "Précis"}

AUDIO_FILTER = "Audio / vidéo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4 *.mkv *.webm);;Tous (*)"
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".mp4", ".mkv", ".webm"}
MIN_RECORDING_S = 0.3
LEVEL_INTERVAL_MS = 33


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, worker: ModelWorker, device_description: str) -> None:
        super().__init__()
        self.settings = settings
        self.worker = worker
        self.recorder = MicRecorder(settings.input_device)
        self.tokens = theme.resolve(settings.theme)
        self.segments: list[Segment] = []
        self.source_name = "transcription"
        self.busy = False  # file / recording transcription in progress
        self.live = False  # live session running (or finishing its final pass)
        self.live_stopping = False
        self.model_ready = False
        self.model_loading = False
        self.record_seconds = 0.0
        self._duration = 0.0

        self.setWindowTitle("MyWhisper")
        self.resize(900, 760)
        self.setMinimumSize(720, 600)
        self.setAcceptDrops(True)
        self._build_ui(device_description)
        self._connect_worker()
        self._apply_icons()

        self.level_timer = QTimer(self, interval=LEVEL_INTERVAL_MS)
        self.level_timer.timeout.connect(self._update_level)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self._theme_changed())
        self.worker.request_load.emit(self.settings.model_key)

    # ---- construction -------------------------------------------------

    def _build_ui(self, device_description: str) -> None:
        t = self.tokens

        # top bar: wordmark, model, language, settings
        wordmark = QLabel("MyWhisper")
        wordmark.setObjectName("Wordmark")
        self.model_control = SegmentedControl([(k, MODEL_LABELS.get(k, s.label)) for k, s in MODELS.items()])
        self.model_control.set_value(self.settings.model_key)
        self.model_control.setToolTip("Turbo : rapide.  Précis : large-v3, plus lent.")
        self.model_control.changed.connect(self._model_changed)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES:
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.language)))
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("IconButton")
        self.settings_button.setToolTip("Réglages")
        self.settings_button.clicked.connect(self._open_settings)

        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(56)
        row = QHBoxLayout(top)
        row.setContentsMargins(20, 0, 12, 0)
        row.setSpacing(10)
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
        card_row = QHBoxLayout()
        card_row.setContentsMargins(24, 8, 24, 16)
        card_row.addWidget(self.transcript)

        # bottom bar: actions, status, device
        self.copy_button = QPushButton("Copier")
        self.copy_button.clicked.connect(self._copy)
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
        self.cancel_button.clicked.connect(self.worker.cancel)
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
        layout.addWidget(top)
        layout.addLayout(capture)
        layout.addLayout(card_row, 1)
        layout.addWidget(bottom)
        self.setCentralWidget(root)

        microphones: list[str] = []
        try:
            microphones = list_input_devices()
        except Exception:
            log.exception("Could not list input devices")
        self.settings_popover = SettingsPopover(self, microphones)
        pop = self.settings_popover
        pop.vad_check.setChecked(self.settings.vad_filter)
        pop.timestamps_check.setChecked(self.settings.show_timestamps)
        pop.mic_combo.setCurrentIndex(max(0, pop.mic_combo.findData(self.settings.input_device)))
        pop.theme_control.set_value(self.settings.theme)
        pop.theme_changed.connect(self._theme_setting_changed)
        pop.timestamps_changed.connect(lambda _: self._rerender())

        self.toast = Toast(root, bottom_offset=52)

        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self._shortcut_capture("record"))
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self._shortcut_capture("live"))
        QShortcut(QKeySequence.StandardKey.Open, self, self._open_file)
        QShortcut(QKeySequence.StandardKey.Save, self, lambda: self._export(".txt"))
        self.addAction(QAction(self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close))
        self._update_controls()

    def _connect_worker(self) -> None:
        w = self.worker
        w.model_loading.connect(self._on_model_loading)
        w.model_loaded.connect(self._on_model_loaded)
        w.transcription_started.connect(self._on_started)
        w.segment_ready.connect(self._on_segment)
        w.transcription_finished.connect(self._on_finished)
        w.live_update.connect(self._on_live_update)
        w.live_finished.connect(self._on_live_finished)
        w.error.connect(self._on_error)

    # ---- theme ---------------------------------------------------------

    def _theme_setting_changed(self, setting: str) -> None:
        self.settings.theme = setting
        self._theme_changed()

    def _theme_changed(self) -> None:
        self.tokens = theme.resolve(self.settings.theme)
        theme.apply(QApplication.instance(), self.tokens)
        theme.apply_titlebar(self, self.tokens)
        for widget in (self.record_button, self.waveform, self.transcript):
            widget.set_tokens(self.tokens)
        self._apply_icons()
        self._rerender()

    def _apply_icons(self) -> None:
        t = self.tokens
        self.settings_button.setIcon(theme.icon("ph.gear-six", t))
        self.settings_button.setIconSize(QSize(20, 20))
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
        if self.idle and not self.recorder.is_recording:
            self.mode_control.set_value(mode)
        self._toggle_capture()

    def _toggle_capture(self) -> None:
        if self.live:
            self._toggle_live()
        elif self.recorder.is_recording:
            self._toggle_recording()
        elif self.mode_control.value() == "live":
            self._toggle_live()
        else:
            self._toggle_recording()

    def _start_microphone(self) -> bool:
        self.recorder.device_name = self.settings_popover.mic_combo.currentData()
        try:
            self.recorder.start()
        except Exception as exc:
            log.exception("Microphone start failed")
            self.transcript.show_error(f"Impossible d'ouvrir le micro : {exc}")
            return False
        self.transcript.hide_error()
        self.record_seconds = 0.0
        self.waveform.set_active(True)
        self.level_timer.start()
        return True

    def _stop_meter(self) -> None:
        self.level_timer.stop()
        self.waveform.set_active(False)

    def _toggle_recording(self) -> None:
        if self.recorder.is_recording:
            self._stop_meter()
            audio = self.recorder.stop()
            self._update_controls()
            if audio.size < MIN_RECORDING_S * SAMPLE_RATE:
                if not self.segments:
                    self.transcript.show_empty()
                self._status("Enregistrement trop court.", 4000)
                return
            self.source_name = "dictee"
            self._start_transcription(audio)
            return
        if self._start_microphone():
            if not self.segments:
                self.transcript.show_empty(LISTENING_RECORD)
            self._status("Enregistrement…")
            self._update_controls()

    def _toggle_live(self) -> None:
        if self.live:
            self.live_stopping = True
            self._status("Fin du direct…")
            self.worker.stop_live()
            self._update_controls()
            return
        if not self._start_microphone():
            return
        self.live = True
        self.segments = []
        self.transcript.clear()
        self.transcript.show_empty(LISTENING_LIVE)
        self.source_name = "direct"
        self._update_controls()
        message = "Parlez, le texte s'affiche au fil de l'eau."
        if self.model_control.value() != "turbo":
            message = "Modèle précis : latence plus élevée en direct."
        self._status(message)
        self.worker.start_live(self.recorder, TranscribeOptions(language=self.language_combo.currentData()))

    def _update_level(self) -> None:
        self.waveform.push(self.recorder.level)
        self.record_seconds += LEVEL_INTERVAL_MS / 1000
        self.timer_label.setText(clock(self.record_seconds))

    # ---- files and transcription ---------------------------------------

    def _open_file(self) -> None:
        if not self.idle or self.recorder.is_recording:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Importer un fichier audio", "", AUDIO_FILTER)
        if path:
            self._transcribe_file(Path(path))

    def _transcribe_file(self, path: Path) -> None:
        if not self.idle or self.recorder.is_recording:
            return
        self.source_name = path.stem
        self._start_transcription(path)

    def _start_transcription(self, audio: AudioSource) -> None:
        self.segments = []
        self.transcript.clear()
        self.transcript.hide_error()
        self.transcript.set_progress(0.0)
        self.busy = True
        self._duration = 0.0
        self._update_controls()
        self._status("Analyse de l'audio…" if self.model_ready else "En attente du modèle…")
        options = TranscribeOptions(
            language=self.language_combo.currentData(),
            vad_filter=self.settings_popover.vad_check.isChecked(),
        )
        self.worker.transcribe(audio, options)

    def _model_changed(self, key: str) -> None:
        self.model_ready = False
        self.worker.request_load.emit(key)

    def _retry_model(self) -> None:
        self.worker.request_load.emit(self.model_control.value())

    # ---- results -------------------------------------------------------

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._plain_text())
        self.toast.show_message("Texte copié")

    def _export(self, suffix: str) -> None:
        if not self.segments or not self.idle:
            return
        exporter = next(e for e in export.exporters() if e.suffix == suffix)
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter la transcription", f"{self.source_name}{suffix}", f"{exporter.label} (*{suffix})"
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(suffix)
        try:
            export.export(target, self.segments)
        except Exception as exc:
            self.transcript.show_error(f"Échec de l'export : {exc}")
            return
        self.toast.show_message(f"Exporté vers {target.name}")

    def _clear(self) -> None:
        self.segments = []
        self.transcript.clear()
        self.transcript.show_empty()
        self._status("")
        self._update_controls()

    def _rerender(self) -> None:
        if not self.live and self.segments:
            self.transcript.render(self.segments, self.settings_popover.timestamps_check.isChecked())

    # ---- worker callbacks ---------------------------------------------

    def _on_model_loading(self, label: str) -> None:
        self.model_loading = True
        self.model_ready = False
        if not self.segments and not self.busy:
            self.transcript.show_loading(label)
        self._status("Chargement du modèle…")
        self._update_controls()

    def _on_model_loaded(self, key: str, device_description: str) -> None:
        self.model_loading = False
        self.model_ready = True
        self.device_chip.setText(device_description)
        if not self.segments and not self.busy:
            self.transcript.show_empty()
        self._status(f"Modèle {MODELS[key].model_name} prêt.", 4000)
        self._update_controls()

    def _on_started(self, info) -> None:
        self._duration = info.duration
        self._status(f"Transcription en cours ({info.language}, {clock(info.duration)})")

    def _on_segment(self, segment: Segment) -> None:
        self.segments.append(segment)
        self.transcript.append_segment(segment, self.settings_popover.timestamps_check.isChecked())
        if self._duration:
            self.transcript.set_progress(segment.end / self._duration)
        self._update_controls()

    def _on_live_update(self, update: LiveUpdate, pass_seconds: float) -> None:
        if not self.live:
            return
        self.segments.extend(update.committed)
        self.transcript.live_update(update.committed, update.provisional)
        if pass_seconds:
            self._status(f"passe {pass_seconds:.2f} s")
        self._update_controls()

    def _on_live_finished(self) -> None:
        self.live = False
        self.live_stopping = False
        self._stop_meter()
        self.recorder.stop()
        self.segments = merge_sentences(self.segments)
        self.transcript.render(self.segments, self.settings_popover.timestamps_check.isChecked())
        self._status(f"Direct terminé · {len(self.segments)} phrase(s)", 6000)
        self._update_controls()

    def _on_finished(self, elapsed: float, duration: float, cancelled: bool) -> None:
        self.busy = False
        self.transcript.set_progress(None)
        if not self.segments:
            self.transcript.show_empty()
        self._update_controls()
        if cancelled:
            self._status("Transcription annulée.", 5000)
            return
        speed = f" · {duration / elapsed:.0f}× temps réel" if elapsed and duration else ""
        self._status(f"{clock(duration)} transcrit en {elapsed:.1f} s{speed}")

    def _on_error(self, message: str) -> None:
        failed_load = self.model_loading
        self.model_loading = False
        self.busy = False
        self.transcript.set_progress(None)
        if not self.segments:
            self.transcript.show_empty()
        self.transcript.show_error(message, "Réessayer" if failed_load else None)
        self._status("")
        self._update_controls()

    # ---- helpers ------------------------------------------------------

    @property
    def idle(self) -> bool:
        return not (self.busy or self.live)

    def status_text(self) -> str:
        return self.status_label.text()

    def _status(self, text: str, timeout_ms: int = 0) -> None:
        self.status_label.setText(text)
        if timeout_ms:
            QTimer.singleShot(timeout_ms, lambda: self.status_label.text() == text and self.status_label.setText(""))

    def _plain_text(self) -> str:
        return "\n".join(s.text for s in self.segments)

    def _update_controls(self) -> None:
        recording = self.recorder.is_recording and not self.live
        capturing = recording or self.live
        self.record_button.set_loading(self.model_loading and not capturing)
        self.record_button.set_active(capturing)
        if capturing:
            self.record_button.setEnabled(not self.live_stopping)  # stays clickable to stop
        else:
            self.record_button.setEnabled(not self.model_loading and not self.busy)
        self.mode_control.setEnabled(self.idle and not recording)
        self.model_control.setEnabled(self.idle and not recording)
        self.language_combo.setEnabled(not capturing)
        self.import_button.setEnabled(self.idle and not recording)
        self.cancel_button.setVisible(self.busy)
        self.live_chip.setVisible(self.live)
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
        if self._audio_url(event) and self.idle and not self.recorder.is_recording:
            event.acceptProposedAction()
            self.transcript.set_drag_active(True)

    def dragLeaveEvent(self, event) -> None:
        self.transcript.set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self.transcript.set_drag_active(False)
        path = self._audio_url(event)
        if path:
            self._transcribe_file(path)

    def _open_settings(self) -> None:
        self.settings_popover.popup_below(self.settings_button)

    def closeEvent(self, event) -> None:
        self.worker.stop_live()
        if self.recorder.is_recording:
            self.recorder.stop()
        pop = self.settings_popover
        self.settings.model_key = self.model_control.value()
        self.settings.mode = self.mode_control.value()
        self.settings.language = self.language_combo.currentData()
        self.settings.vad_filter = pop.vad_check.isChecked()
        self.settings.show_timestamps = pop.timestamps_check.isChecked()
        self.settings.input_device = pop.mic_combo.currentData()
        try:
            self.settings.save()
        except OSError:
            log.exception("Could not save settings")
        self.worker.shutdown()
        super().closeEvent(event)
