from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from mywhisper.ui.theme import Tokens

BAR_WIDTH = 3.0
BAR_GAP = 3.0


class WaveformView(QWidget):
    """Scrolling history of microphone levels, newest on the right."""

    def __init__(self, tokens: Tokens, bars: int = 60, parent=None) -> None:
        super().__init__(parent)
        self._t = tokens
        self._levels: deque[float] = deque([0.0] * bars, maxlen=bars)
        self._active = False
        self.setFixedHeight(40)
        self.setMinimumWidth(int(bars * (BAR_WIDTH + BAR_GAP)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), 40)

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self.clear()
        self.update()

    def push(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, level)))
        self.update()

    def clear(self) -> None:
        self._levels.extend([0.0] * self._levels.maxlen)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        color = self._t.qcolor("accent") if self._active else self._t.qcolor("border")
        p.setBrush(color)
        count = len(self._levels)
        total = count * (BAR_WIDTH + BAR_GAP) - BAR_GAP
        x = (self.width() - total) / 2
        mid = self.height() / 2
        for level in self._levels:
            # sqrt lifts quiet speech so it stays visible next to loud peaks
            h = max(BAR_WIDTH, (level**0.5) * (self.height() - 4))
            p.drawRoundedRect(QRectF(x, mid - h / 2, BAR_WIDTH, h), BAR_WIDTH / 2, BAR_WIDTH / 2)
            x += BAR_WIDTH + BAR_GAP
