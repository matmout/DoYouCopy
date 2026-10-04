from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mywhisper.ui import theme
from mywhisper.ui.widgets.segmented import SegmentedControl

THEMES = [("auto", "Système"), ("dark", "Sombre"), ("light", "Clair")]
DICTATION_MODES = [("hold", "Maintenir"), ("toggle", "Basculer")]
DICTATION_OUTPUTS = [("paste", "Coller dans l'application active"), ("clipboard", "Copier seulement")]


class SettingsPopover(QWidget):
    """Secondary settings, kept off the main screen: transcription, dictation, microphone, theme."""

    theme_changed = Signal(str)
    timestamps_changed = Signal(bool)
    vocabulary_requested = Signal()
    hotkey_edited = Signal(str)  # portable text, e.g. "Ctrl+Shift+Space"
    visibility_changed = Signal(bool)  # the dictation hotkey is suspended while open

    def __init__(self, parent: QWidget, microphones: list[str]) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        panel = QFrame(self)
        panel.setObjectName("Popover")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self.vad_check = QCheckBox("Ignorer les silences (VAD)")
        self.vad_check.setToolTip("Pour les fichiers et les enregistrements. Le mode Direct l'utilise toujours.")
        self.timestamps_check = QCheckBox("Afficher l'horodatage")
        self.timestamps_check.toggled.connect(self.timestamps_changed)
        self.vocabulary_button = QPushButton("Vocabulaire…")
        self.vocabulary_button.setToolTip("Mots à favoriser, remplacements, commandes vocales")
        self.vocabulary_button.clicked.connect(self._request_vocabulary)
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Micro par défaut", None)
        for name in microphones:
            self.mic_combo.addItem(name, name)
        self.mic_combo.setMinimumWidth(260)
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumSequenceLength(1)
        for line in self.hotkey_edit.findChildren(QLineEdit):
            line.setPlaceholderText("Appuyez sur un raccourci")
        self.hotkey_edit.setToolTip("Raccourci de dictée, actif dans toutes les applications")
        self.hotkey_edit.editingFinished.connect(
            lambda: self.hotkey_edited.emit(
                self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            )
        )
        self.dictation_mode_control = SegmentedControl(DICTATION_MODES)
        self.dictation_mode_control.setToolTip(
            "Maintenir : parlez tant que la touche est enfoncée.  Basculer : un appui pour démarrer, un pour arrêter."
        )
        hotkey_row = QHBoxLayout()
        hotkey_row.setContentsMargins(0, 0, 0, 0)
        hotkey_row.addWidget(self.hotkey_edit, 1)
        hotkey_row.addWidget(self.dictation_mode_control)
        self.hotkey_row = QWidget()
        self.hotkey_row.setLayout(hotkey_row)
        self.output_combo = QComboBox()
        for value, label in DICTATION_OUTPUTS:
            self.output_combo.addItem(label, value)
        self.sounds_check = QCheckBox("Signal sonore au début et à la fin")
        self.tray_check = QCheckBox("Rester dans la zone de notification à la fermeture")
        self.autostart_check = QCheckBox("Démarrer avec Windows")
        self.theme_control = SegmentedControl(THEMES)
        self.theme_control.changed.connect(lambda value: self.theme_changed.emit(value))

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(8)
        for title, widget in (
            ("Transcription", None),
            (None, self.vad_check),
            (None, self.timestamps_check),
            (None, self.vocabulary_button),
            ("Dictée (toutes applications)", self.hotkey_row),
            (None, self.output_combo),
            (None, self.sounds_check),
            (None, self.tray_check),
            (None, self.autostart_check),
            ("Micro", self.mic_combo),
            ("Thème", self.theme_control),
        ):
            if title:
                label = QLabel(title)
                label.setObjectName("PopoverTitle")
                if layout.count():
                    layout.addSpacing(6)
                layout.addWidget(label)
            if widget is not None:
                layout.addWidget(widget)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self, duration=150)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, event) -> None:
        self.visibility_changed.emit(True)
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self.visibility_changed.emit(False)
        super().hideEvent(event)

    def _request_vocabulary(self) -> None:
        self.hide()
        self.vocabulary_requested.emit()

    def popup_below(self, anchor: QWidget) -> None:
        self.adjustSize()
        corner = anchor.mapToGlobal(QPoint(anchor.width(), anchor.height() + 6))
        self.move(corner - QPoint(self.width(), 0))
        if theme.animations_enabled():
            self.setWindowOpacity(0.0)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.show()
