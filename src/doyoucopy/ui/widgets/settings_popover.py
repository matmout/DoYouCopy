from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from doyoucopy.i18n import N_, tr
from doyoucopy.ui import theme
from doyoucopy.ui.widgets.segmented import SegmentedControl

THEMES = [("auto", N_("Système")), ("dark", N_("Sombre")), ("light", N_("Clair"))]


class SettingsPopover(QWidget):
    """Quick settings at hand; everything else is in the Settings window."""

    theme_changed = Signal(str)
    timestamps_changed = Signal(bool)
    vocabulary_requested = Signal()
    all_settings_requested = Signal()

    def __init__(self, parent: QWidget, microphones: list[str]) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        panel = QFrame(self)
        panel.setObjectName("Popover")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self.vad_check = QCheckBox(tr("Ignorer les silences (VAD)"))
        self.vad_check.setToolTip(tr("Pour les fichiers et les enregistrements. Le mode Direct l'utilise toujours."))
        self.timestamps_check = QCheckBox(tr("Afficher l'horodatage"))
        self.timestamps_check.toggled.connect(self.timestamps_changed)
        self.vocabulary_button = QPushButton(tr("Vocabulaire…"))
        self.vocabulary_button.setToolTip(tr("Mots à favoriser, remplacements, commandes vocales"))
        self.vocabulary_button.clicked.connect(lambda: self._close_then(self.vocabulary_requested))
        self.mic_combo = QComboBox()
        self.mic_combo.addItem(tr("Micro par défaut"), None)
        for name in microphones:
            self.mic_combo.addItem(name, name)
        self.mic_combo.setMinimumWidth(260)
        self.theme_control = SegmentedControl([(value, tr(label)) for value, label in THEMES])
        self.theme_control.changed.connect(lambda value: self.theme_changed.emit(value))
        self.all_button = QPushButton(tr("Tous les réglages…"))
        self.all_button.setObjectName("OutlineButton")
        self.all_button.clicked.connect(lambda: self._close_then(self.all_settings_requested))

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(8)
        for title, widget in (
            (N_("Transcription"), None),
            (None, self.vad_check),
            (None, self.timestamps_check),
            (None, self.vocabulary_button),
            (N_("Micro"), self.mic_combo),
            (N_("Thème"), self.theme_control),
        ):
            if title:
                label = QLabel(tr(title))
                label.setObjectName("PopoverTitle")
                if layout.count():
                    layout.addSpacing(6)
                layout.addWidget(label)
            if widget is not None:
                layout.addWidget(widget)
        layout.addSpacing(10)
        layout.addWidget(self.all_button)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self, duration=150)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _close_then(self, signal) -> None:
        self.hide()
        signal.emit()

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
