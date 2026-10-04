from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mywhisper.ui.theme import Tokens
from mywhisper.ui.widgets.waveform import WaveformView

LEVEL_INTERVAL_MS = 33
BOTTOM_MARGIN = 28
MESSAGE_MS = 1600


class DictationOverlay(QWidget):
    """Floating pill shown during a universal dictation.

    It must never take the focus: the text is pasted into the window that has it.
    """

    def __init__(self, tokens: Tokens) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._t = tokens
        self._level_source: Callable[[], float] | None = None

        self.pill = QFrame(self)
        self.pill.setObjectName("DictationPill")
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.waveform = WaveformView(tokens, bars=28)
        self.waveform.setFixedHeight(28)
        self.label = QLabel()
        self.hint = QLabel("Échap pour annuler")

        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(self.label)
        texts.addWidget(self.hint)
        row = QHBoxLayout(self.pill)
        row.setContentsMargins(16, 8, 18, 8)
        row.setSpacing(12)
        row.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.waveform, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(texts)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.pill)

        self._level_timer = QTimer(self, interval=LEVEL_INTERVAL_MS)
        self._level_timer.timeout.connect(self._pull_level)
        self._hide_timer = QTimer(self, singleShot=True, interval=MESSAGE_MS)
        self._hide_timer.timeout.connect(self.hide)
        self.set_tokens(tokens)

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        self.waveform.set_tokens(tokens)
        self._style(error=False)

    def _style(self, error: bool, dot_token: str = "accent") -> None:
        t = self._t
        self.pill.setStyleSheet(
            f"#DictationPill {{ background: {t.elevated}; border: 1px solid "
            f"{t.accent if error else t.border}; border-radius: 22px; }}"
        )
        self.dot.setStyleSheet(f"background: {getattr(t, dot_token)}; border-radius: 5px;")
        self.label.setStyleSheet(f"color: {t.text}; font-weight: 600;")
        self.hint.setStyleSheet(f"color: {t.muted}; font-size: 8.5pt;")

    # ---- states --------------------------------------------------------

    def show_listening(self, level_source: Callable[[], float]) -> None:
        self._level_source = level_source
        self._style(error=False, dot_token="accent")
        self.label.setText("Écoute…")
        self.hint.setText("Échap pour annuler")
        self.hint.show()
        self.waveform.set_active(True)
        self.waveform.show()
        self._level_timer.start()
        self._present(sticky=True)

    def show_transcribing(self) -> None:
        self._stop_levels()
        self._style(error=False, dot_token="muted")
        self.label.setText("Transcription…")
        self.hint.show()
        self._present(sticky=True)

    def show_message(self, text: str, error: bool = False) -> None:
        self._stop_levels()
        self.waveform.hide()
        self._style(error=error, dot_token="accent" if error else "muted")
        self.label.setText(text)
        self.hint.hide()
        self._present(sticky=False)

    def dismiss(self) -> None:
        self._stop_levels()
        self.hide()

    # ---- internals -----------------------------------------------------

    def _stop_levels(self) -> None:
        self._level_timer.stop()
        self._level_source = None
        self.waveform.set_active(False)

    def _pull_level(self) -> None:
        if self._level_source is not None:
            self.waveform.push(self._level_source())

    def _present(self, sticky: bool) -> None:
        self._hide_timer.stop()
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()  # above the taskbar
        self.move(QPoint(area.center().x() - self.width() // 2, area.bottom() - self.height() - BOTTOM_MARGIN))
        if not self.isVisible():
            self.show()
        self.raise_()
        if not sticky:
            self._hide_timer.start()
