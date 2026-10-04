from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from mywhisper.ui import theme

VISIBLE_MS = 2500
MARGIN = 16


class Toast(QLabel):
    """Short confirmation ("Copié", "Exporté…") anchored bottom-right of its parent."""

    def __init__(self, parent: QWidget, bottom_offset: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self._bottom_offset = bottom_offset
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self, duration=180)
        self._slide = QPropertyAnimation(self, b"pos", self, duration=180)
        for anim in (self._fade, self._slide):
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self, singleShot=True, interval=VISIBLE_MS)
        self._timer.timeout.connect(self._dismiss)
        self.hide()

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        target = QPoint(
            parent.width() - self.width() - MARGIN,
            parent.height() - self.height() - MARGIN - self._bottom_offset,
        )
        self.raise_()
        self.show()
        if theme.animations_enabled():
            self._slide.setStartValue(target + QPoint(0, 8))
            self._slide.setEndValue(target)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._slide.start()
            self._fade.start()
        else:
            self.move(target)
            self._opacity.setOpacity(1.0)
        self._timer.start()

    def _dismiss(self) -> None:
        if not theme.animations_enabled():
            self.hide()
            return
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._hide_once)
        self._fade.start()

    def _hide_once(self) -> None:
        self._fade.finished.disconnect(self._hide_once)
        self.hide()
