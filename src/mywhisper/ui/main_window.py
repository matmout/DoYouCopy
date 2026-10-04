from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import (
    QAction,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QKeySequence,
    QPalette,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mywhisper import export
from mywhisper.audio.recorder import MicRecorder, list_input_devices
from mywhisper.config import Settings
from mywhisper.core.live import SENTENCE_END, LiveUpdate, merge_sentences
from mywhisper.core.models import MODELS
from mywhisper.core.types import SAMPLE_RATE, AudioSource, Segment, TranscribeOptions, Word
from mywhisper.ui.workers import ModelWorker

log = logging.getLogger(__name__)

LANGUAGES = [
    (None, "Détection auto"),
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

AUDIO_FILTER = "Audio / vidéo (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.wma *.mp4 *.mkv *.webm);;Tous (*)"
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".mp4", ".mkv", ".webm"}
MIN_RECORDING_S = 0.3


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, worker: ModelWorker, device_description: str) -> None:
        super().__init__()
        self.settings = settings
        self.worker = worker
        self.recorder = MicRecorder(settings.input_device)
        self.segments: list[Segment] = []
        self.source_name = "transcription"
        self.busy = False
        self.model_ready = False
        self.live = False  # live session running (or finishing its final pass)
        self._provisional_start = 0  # text position where the provisional live text begins
        self._live_last = ""  # last committed live word, to choose the next separator

        self.setWindowTitle("MyWhisper")
        self.resize(820, 560)
        self.setAcceptDrops(True)
        self._build_ui(device_description)
        self._connect_worker()

        self.level_timer = QTimer(self, interval=50)
        self.level_timer.timeout.connect(self._update_recording)
        self.worker.request_load.emit(self.settings.model_key)

    # ---- construction -------------------------------------------------

    def _build_ui(self, device_description: str) -> None:
        self.record_button = QPushButton("● Enregistrer")
        self.record_button.setShortcut(QKeySequence("Ctrl+R"))
        self.record_button.clicked.connect(self._toggle_recording)
        self.live_button = QPushButton("◉ Direct")
        self.live_button.setShortcut(QKeySequence("Ctrl+L"))
        self.live_button.setToolTip("Transcription en temps réel pendant que vous parlez (Ctrl+L)")
        self.live_button.clicked.connect(self._toggle_live)
        self.open_button = QPushButton("Ouvrir un fichier…")
        self.open_button.setShortcut(QKeySequence.StandardKey.Open)
        self.open_button.clicked.connect(self._open_file)
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.clicked.connect(self.worker.cancel)
        self.cancel_button.hide()

        self.model_combo = QComboBox()
        for spec in MODELS.values():
            self.model_combo.addItem(spec.label, spec.key)
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(self.settings.model_key)))
        self.model_combo.currentIndexChanged.connect(self._model_changed)

        self.language_combo = QComboBox()
        for code, name in LANGUAGES:
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(self.settings.language)))

        self.vad_check = QCheckBox("Filtrer les silences (VAD)")
        self.vad_check.setChecked(self.settings.vad_filter)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Micro par défaut", None)
        try:
            for name in list_input_devices():
                self.mic_combo.addItem(name, name)
        except Exception:
            log.exception("Could not list input devices")
        self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(self.settings.input_device)))
        self.mic_combo.setMaximumWidth(260)

        actions = QHBoxLayout()
        actions.addWidget(self.record_button)
        actions.addWidget(self.live_button)
        actions.addWidget(self.open_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        actions.addWidget(QLabel("Micro :"))
        actions.addWidget(self.mic_combo)

        options = QHBoxLayout()
        options.addWidget(QLabel("Modèle :"))
        options.addWidget(self.model_combo)
        options.addSpacing(12)
        options.addWidget(QLabel("Langue :"))
        options.addWidget(self.language_combo)
        options.addSpacing(12)
        options.addWidget(self.vad_check)
        options.addStretch()

        self.level_bar = QProgressBar(maximum=100, textVisible=False)
        self.level_bar.setFixedHeight(6)
        self.level_bar.hide()

        self.text = QPlainTextEdit(readOnly=True)
        self.text.setPlaceholderText(
            "Enregistrez avec le micro (Ctrl+R) ou ouvrez / déposez un fichier audio."
        )
        font = self.text.font()
        font.setPointSize(font.pointSize() + 2)
        self.text.setFont(font)

        self.timestamps_check = QCheckBox("Horodatage")
        self.timestamps_check.setChecked(self.settings.show_timestamps)
        self.timestamps_check.toggled.connect(self._render_text)
        self.copy_button = QPushButton("Copier")
        self.copy_button.clicked.connect(self._copy)
        self.export_button = QPushButton("Exporter…")
        self.export_button.setShortcut(QKeySequence.StandardKey.Save)
        self.export_button.clicked.connect(self._export)
        self.clear_button = QPushButton("Effacer")
        self.clear_button.clicked.connect(self._clear)

        bottom = QHBoxLayout()
        bottom.addWidget(self.timestamps_check)
        bottom.addStretch()
        bottom.addWidget(self.copy_button)
        bottom.addWidget(self.export_button)
        bottom.addWidget(self.clear_button)

        layout = QVBoxLayout()
        layout.addLayout(actions)
        layout.addLayout(options)
        layout.addWidget(self.level_bar)
        layout.addWidget(self.text, 1)
        layout.addLayout(bottom)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.device_label = QLabel(device_description)
        self.statusBar().addPermanentWidget(self.device_label)

        quit_action = QAction(self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close)
        self.addAction(quit_action)
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

    # ---- actions ------------------------------------------------------

    def _toggle_recording(self) -> None:
        if self.recorder.is_recording:
            self._stop_recording()
            return
        self.recorder.device_name = self.mic_combo.currentData()
        try:
            self.recorder.start()
        except Exception as exc:
            log.exception("Microphone start failed")
            QMessageBox.warning(self, "Micro", f"Impossible d'ouvrir le micro :\n{exc}")
            return
        self.record_seconds = 0.0
        self.level_bar.show()
        self.level_timer.start()
        self._update_controls()

    def _stop_recording(self) -> None:
        self.level_timer.stop()
        self.level_bar.hide()
        audio = self.recorder.stop()
        self._update_controls()
        if audio.size < MIN_RECORDING_S * SAMPLE_RATE:
            self.statusBar().showMessage("Enregistrement trop court.", 4000)
            return
        self.source_name = "dictee"
        self._start_transcription(audio)

    def _update_recording(self) -> None:
        self.level_bar.setValue(int(self.recorder.level * 100))
        self.record_seconds += self.level_timer.interval() / 1000
        if not self.live:
            self.statusBar().showMessage(f"Enregistrement… {_clock(self.record_seconds)}")

    def _toggle_live(self) -> None:
        if self.live:
            self.live_button.setEnabled(False)
            self.statusBar().showMessage("Fin du direct…")
            self.worker.stop_live()
            return
        self.recorder.device_name = self.mic_combo.currentData()
        try:
            self.recorder.start()
        except Exception as exc:
            log.exception("Microphone start failed")
            QMessageBox.warning(self, "Micro", f"Impossible d'ouvrir le micro :\n{exc}")
            return
        self.live = True
        self.segments = []
        self.text.clear()
        self._provisional_start = 0
        self._live_last = ""
        self.source_name = "direct"
        self.record_seconds = 0.0
        self.level_bar.show()
        self.level_timer.start()
        self._update_controls()
        message = "Direct : parlez, le texte s'affiche au fil de l'eau."
        if self.model_combo.currentData() != "turbo":
            message += " (modèle précis : latence plus élevée)"
        self.statusBar().showMessage(message)
        options = TranscribeOptions(language=self.language_combo.currentData())
        self.worker.start_live(self.recorder, options)

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un fichier audio", "", AUDIO_FILTER)
        if path:
            self._transcribe_file(Path(path))

    def _transcribe_file(self, path: Path) -> None:
        if self.busy or self.recorder.is_recording:
            return
        self.source_name = path.stem
        self._start_transcription(path)

    def _start_transcription(self, audio: AudioSource) -> None:
        self.segments = []
        self.text.clear()
        self.busy = True
        self._update_controls()
        if not self.model_ready:
            self.statusBar().showMessage("Transcription en attente du chargement du modèle…")
        else:
            self.statusBar().showMessage("Analyse de l'audio…")
        options = TranscribeOptions(
            language=self.language_combo.currentData(), vad_filter=self.vad_check.isChecked()
        )
        self.worker.transcribe(audio, options)

    def _model_changed(self) -> None:
        self.model_ready = False
        self._update_controls()
        self.worker.request_load.emit(self.model_combo.currentData())

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._plain_text())
        self.statusBar().showMessage("Texte copié dans le presse-papiers.", 3000)

    def _export(self) -> None:
        filters = ";;".join(f"{e.label} (*{e.suffix})" for e in export.exporters())
        path, chosen = QFileDialog.getSaveFileName(
            self, "Exporter la transcription", f"{self.source_name}.txt", filters
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            suffix = next((e.suffix for e in export.exporters() if e.suffix in chosen), ".txt")
            target = target.with_suffix(suffix)
        try:
            export.export(target, self.segments)
        except Exception as exc:
            QMessageBox.warning(self, "Export", f"Échec de l'export :\n{exc}")
            return
        self.statusBar().showMessage(f"Exporté : {target}", 5000)

    def _clear(self) -> None:
        self.segments = []
        self.text.clear()
        self._update_controls()

    # ---- worker callbacks ---------------------------------------------

    def _on_model_loading(self, label: str) -> None:
        self.statusBar().showMessage(f"Chargement du modèle {label}…")

    def _on_model_loaded(self, key: str, device_description: str) -> None:
        self.model_ready = True
        self.device_label.setText(device_description)
        self.statusBar().showMessage(f"Modèle {MODELS[key].label} prêt.", 4000)
        self._update_controls()

    def _on_started(self, info) -> None:
        self.statusBar().showMessage(
            f"Transcription… langue : {info.language} ({info.language_probability:.0%}), "
            f"durée : {_clock(info.duration)}"
        )

    def _on_segment(self, segment: Segment) -> None:
        self.segments.append(segment)
        self.text.appendPlainText(self._format(segment))
        self._update_controls()

    def _on_live_update(self, update: LiveUpdate, pass_seconds: float) -> None:
        if not self.live:
            return
        self.segments.extend(update.committed)
        # Committed words are appended; the provisional tail is replaced on every pass.
        cursor = self.text.textCursor()
        cursor.setPosition(self._provisional_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        normal = QTextCharFormat()
        for segment in update.committed:
            for word in segment.words or (Word(segment.start, segment.end, " " + segment.text),):
                cursor.insertText(self._live_join(word.text), normal)
                self._live_last = word.text
        self._provisional_start = cursor.position()
        if update.provisional:
            provisional = QTextCharFormat()
            provisional.setForeground(self.text.palette().color(QPalette.ColorRole.PlaceholderText))
            provisional.setFontItalic(True)
            cursor.insertText(self._live_join(" " + update.provisional), provisional)
        scrollbar = self.text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if pass_seconds:
            self.statusBar().showMessage(
                f"Direct… {_clock(self.record_seconds)} · passe GPU {pass_seconds:.2f} s"
            )
        self._update_controls()

    def _live_join(self, word: str) -> str:
        """Whisper words carry their leading space; a finished sentence starts a new line."""
        if not self._live_last:
            return word.lstrip()
        if self._live_last.rstrip().endswith(SENTENCE_END):
            return "\n" + word.lstrip()
        return word

    def _on_live_finished(self) -> None:
        self.live = False
        self.level_timer.stop()
        self.level_bar.hide()
        self.recorder.stop()
        self.segments = merge_sentences(self.segments)
        self._render_text()
        self.statusBar().showMessage(f"Direct terminé : {len(self.segments)} segment(s).", 5000)
        self._update_controls()

    def _on_finished(self, elapsed: float, duration: float, cancelled: bool) -> None:
        self.busy = False
        self._update_controls()
        if cancelled:
            self.statusBar().showMessage("Transcription annulée.", 5000)
            return
        rtf = elapsed / duration if duration else 0
        self.statusBar().showMessage(
            f"Terminé : {duration:.1f} s d'audio en {elapsed:.1f} s "
            f"({1 / rtf:.0f}× temps réel)" if rtf else f"Terminé en {elapsed:.1f} s"
        )

    def _on_error(self, message: str) -> None:
        self.busy = False
        self._update_controls()
        self.statusBar().clearMessage()
        QMessageBox.warning(self, "MyWhisper", message)

    # ---- helpers ------------------------------------------------------

    def _format(self, segment: Segment) -> str:
        if self.timestamps_check.isChecked():
            return f"[{_clock(segment.start)} → {_clock(segment.end)}]  {segment.text}"
        return segment.text

    def _plain_text(self) -> str:
        return "\n".join(s.text for s in self.segments)

    def _render_text(self) -> None:
        self.text.setPlainText("\n".join(self._format(s) for s in self.segments))
        self._provisional_start = self.text.document().characterCount() - 1

    def _update_controls(self) -> None:
        recording = self.recorder.is_recording and not self.live
        idle = not (self.busy or self.live)
        self.record_button.setText("■ Arrêter" if recording else "● Enregistrer")
        self.record_button.setEnabled(not self.busy and not self.live)
        self.live_button.setText("■ Arrêter le direct" if self.live else "◉ Direct")
        if not self.live:
            self.live_button.setEnabled(idle and not recording)
        self.open_button.setEnabled(idle and not recording)
        self.cancel_button.setVisible(self.busy)
        self.model_combo.setEnabled(idle)
        self.language_combo.setEnabled(not self.live)
        self.mic_combo.setEnabled(not self.recorder.is_recording)
        has_text = bool(self.segments)
        self.copy_button.setEnabled(has_text)
        self.export_button.setEnabled(has_text and idle)
        self.clear_button.setEnabled(has_text and idle)

    # ---- Qt events ----------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).suffix.lower() in AUDIO_SUFFIXES:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self._transcribe_file(Path(event.mimeData().urls()[0].toLocalFile()))

    def closeEvent(self, event) -> None:
        self.worker.stop_live()
        if self.recorder.is_recording:
            self.recorder.stop()
        self.settings.model_key = self.model_combo.currentData()
        self.settings.language = self.language_combo.currentData()
        self.settings.vad_filter = self.vad_check.isChecked()
        self.settings.show_timestamps = self.timestamps_check.isChecked()
        self.settings.input_device = self.mic_combo.currentData()
        try:
            self.settings.save()
        except OSError:
            log.exception("Could not save settings")
        self.worker.shutdown()
        super().closeEvent(event)
