from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton

from doyoucopy.i18n import tr
from doyoucopy.ui import theme
from doyoucopy.ui.theme import Tokens

DIAMETER = 84
HALO = 22  # room around the circle for the pulse ring


class RecordButton(QAbstractButton):
    """Large round capture button.

    idle: accent disc + microphone; active: accent disc + stop square and a pulsing
    halo (signals that the microphone is live); loading: neutral disc + spinner arc.
    """

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self._t = tokens
        self._active = False
        self._loading = False
        self._scale = 1.0
        self._pulse = 0.0
        self._spin = 0.0
        self._animate = theme.animations_enabled()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.sizeHint())

        self._press_anim = QVariantAnimation(self, duration=120)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim.valueChanged.connect(self._set_scale)
        self.pressed.connect(lambda: self._animate_scale(0.94))
        self.released.connect(lambda: self._animate_scale(1.0))

        self._pulse_anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1400)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pulse_anim.valueChanged.connect(self._set_pulse)

        self._spin_anim = QVariantAnimation(self, startValue=0.0, endValue=360.0, duration=900)
        self._spin_anim.setLoopCount(-1)
        self._spin_anim.valueChanged.connect(self._set_spin)

    def sizeHint(self) -> QSize:
        side = DIAMETER + 2 * HALO
        return QSize(side, side)

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        self.update()

    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setAccessibleName(tr("Arrêter") if active else tr("Démarrer la capture"))
        if active and self._animate:
            self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
            self._pulse = 0.0
        self.update()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.setEnabled(not loading)
        if loading and self._animate:
            self._spin_anim.start()
        else:
            self._spin_anim.stop()
        self.update()

    # ---- animation plumbing -------------------------------------------

    def _animate_scale(self, target: float) -> None:
        if not self._animate:
            return
        self._press_anim.stop()
        self._press_anim.setStartValue(self._scale)
        self._press_anim.setEndValue(target)
        self._press_anim.start()

    def _set_scale(self, value) -> None:
        self._scale = float(value)
        self.update()

    def _set_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def _set_spin(self, value) -> None:
        self._spin = float(value)
        self.update()

    # ---- painting ------------------------------------------------------

    def paintEvent(self, event) -> None:
        t = self._t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = DIAMETER / 2 * self._scale

        if self._active:
            if self._animate:
                ring = radius + 4 + HALO * self._pulse
                p.setPen(QPen(t.qcolor("accent", 0.55 * (1 - self._pulse)), 2))
            else:
                ring = radius + 8
                p.setPen(QPen(t.qcolor("accent", 0.4), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, ring, ring)

        enabled = self.isEnabled()
        fill = t.qcolor("accent") if enabled else t.qcolor("elevated")
        if enabled and self.underMouse() and not self.isDown():
            fill = fill.lighter(108) if t.is_dark else fill.darker(106)
        p.setPen(QPen(t.qcolor("border"), 1) if not enabled else Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(center, radius, radius)

        if self.hasFocus() and self.focusPolicy() != Qt.FocusPolicy.NoFocus and enabled:
            p.setPen(QPen(t.qcolor("text", 0.8), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, radius + 5, radius + 5)

        if self._loading:
            pen = QPen(t.qcolor("accent"), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            arc = QRectF(center.x() - radius + 6, center.y() - radius + 6, 2 * radius - 12, 2 * radius - 12)
            p.drawArc(arc, int(-self._spin * 16), 90 * 16)
            return

        glyph_color = t.on_accent if enabled else t.muted
        if self._active:
            side = radius * 0.62
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.qcolor("on_accent"))
            p.drawRoundedRect(QRectF(center.x() - side / 2, center.y() - side / 2, side, side), 4, 4)
        else:
            import qtawesome as qta

            size = int(radius * 0.95)
            pixmap = qta.icon("ph.microphone-fill", color=glyph_color).pixmap(size, size)
            p.drawPixmap(int(center.x() - size / 2), int(center.y() - size / 2), pixmap)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)
