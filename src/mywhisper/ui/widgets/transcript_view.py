from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QLinearGradient, QPainter, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mywhisper.core.live import SENTENCE_END
from mywhisper.core.types import Segment, Word
from mywhisper.ui import theme
from mywhisper.ui.theme import Tokens

READY = (
    "Prêt à transcrire",
    "Cliquez sur le micro ou appuyez sur Ctrl+R.\nVous pouvez aussi déposer un fichier audio ici.",
)
LISTENING_RECORD = ("À l'écoute", "Cliquez à nouveau sur le bouton pour arrêter et transcrire.")
LISTENING_LIVE = ("À l'écoute", "Le texte apparaîtra dès les premiers mots.")
READING_CHARS = 72
LINE_HEIGHT = 155  # percent


def clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


class _ReadingEdit(QTextEdit):
    """Read-only text centred in a column of ~72 characters, the comfortable reading width."""

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.setFont(theme.ui_font(12))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_column()

    def clear(self) -> None:
        super().clear()  # resets the document, and with it the root frame margins
        self.apply_column()

    def apply_column(self) -> None:
        column = self.fontMetrics().averageCharWidth() * READING_CHARS
        side = max(24, (self.viewport().width() - column) / 2)
        frame = self.document().rootFrame()
        fmt = frame.frameFormat()
        fmt.setLeftMargin(side)
        fmt.setRightMargin(side)
        fmt.setTopMargin(24)
        fmt.setBottomMargin(24)
        frame.setFrameFormat(fmt)


class _Skeleton(QWidget):
    """Placeholder lines with a moving sheen while the model loads."""

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self._t = tokens
        self._phase = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1300)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._tick)
        self.label = QLabel("", self)
        self.label.setProperty("muted", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 150, 0, 0)  # below the painted lines
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens

    def showEvent(self, event) -> None:
        if theme.animations_enabled():
            self._anim.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._anim.stop()
        super().hideEvent(event)

    def _tick(self, value) -> None:
        self._phase = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        width = min(self.width() - 64, 560)
        x0 = (self.width() - width) / 2
        sheen = x0 - 200 + (width + 400) * self._phase
        for i, fraction in enumerate((0.92, 0.78, 0.55)):
            rect = QRectF(x0, 40 + i * 30, width * fraction, 12)
            gradient = QLinearGradient(sheen - 120, 0, sheen + 120, 0)
            gradient.setColorAt(0, self._t.qcolor("elevated"))
            gradient.setColorAt(0.5, self._t.qcolor("border"))
            gradient.setColorAt(1, self._t.qcolor("elevated"))
            p.setBrush(gradient)
            p.drawRoundedRect(rect, 6, 6)


class _Empty(QWidget):
    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = title = QLabel()
        title.setObjectName("EmptyTitle")
        self.hint = hint = QLabel()
        hint.setProperty("muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_message(*READY)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.icon)
        layout.addSpacing(6)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.set_tokens(tokens)

    def set_tokens(self, tokens: Tokens) -> None:
        self.icon.setPixmap(theme.icon("ph.microphone", tokens, "muted").pixmap(36, 36))

    def set_message(self, title: str, hint: str) -> None:
        self.title.setText(title)
        self.hint.setText(hint)


class _Banner(QFrame):
    action = Signal()

    def __init__(self, tokens: Tokens) -> None:
        super().__init__()
        self.setObjectName("Banner")
        self.icon = QLabel()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.action_button = QPushButton()
        self.action_button.setObjectName("OutlineButton")
        self.action_button.clicked.connect(self.action)
        self.close_button = QPushButton()
        self.close_button.setObjectName("IconButton")
        self.close_button.setToolTip("Fermer")
        self.close_button.clicked.connect(self.hide)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 8, 10)
        layout.setSpacing(10)
        layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.action_button)
        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.set_tokens(tokens)
        self.hide()

    def set_tokens(self, tokens: Tokens) -> None:
        self.icon.setPixmap(theme.icon("ph.warning", tokens, "accent").pixmap(18, 18))
        self.close_button.setIcon(theme.icon("ph.x", tokens, "muted"))

    def show_message(self, text: str, action: str | None) -> None:
        self.message.setText(text)
        self.action_button.setVisible(bool(action))
        self.action_button.setText(action or "")
        self.show()


class TranscriptView(QFrame):
    """The transcript card: empty, loading and error states, final and live rendering."""

    retry_requested = Signal()

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TranscriptCard")
        self._t = tokens
        self._animate = theme.animations_enabled()

        self.progress = QProgressBar()
        self.progress.setObjectName("ThinProgress")
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(2)
        self.progress.hide()

        self.banner = _Banner(tokens)
        self.banner.action.connect(self.retry_requested)
        self.banner.action.connect(self.banner.hide)

        self.empty = _Empty(tokens)
        self.skeleton = _Skeleton(tokens)
        self.editor = _ReadingEdit()
        self.pages = QStackedWidget()
        for page in (self.empty, self.skeleton, self.editor):
            self.pages.addWidget(page)

        banner_row = QHBoxLayout()
        banner_row.setContentsMargins(12, 12, 12, 0)
        banner_row.addWidget(self.banner)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(self.progress)
        layout.addLayout(banner_row)
        layout.addWidget(self.pages, 1)

        self._block = QTextBlockFormat()
        self._block.setLineHeight(LINE_HEIGHT, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        self._block.setBottomMargin(6)
        self._provisional_start = 0
        self._live_last = ""
        self._fade = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=200)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._fade_step)
        self._fade.finished.connect(self._fade_done)
        self._fade_range = (0, 0)
        self.show_empty()

    # ---- states --------------------------------------------------------

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        for part in (self.empty, self.skeleton, self.banner):
            part.set_tokens(tokens)

    def show_empty(self, message: tuple[str, str] = READY) -> None:
        self.empty.set_message(*message)
        self.pages.setCurrentWidget(self.empty)

    def show_loading(self, label: str) -> None:
        self.show_loading_text(f"Chargement de {label}…")

    def set_font_size(self, points: int) -> None:
        self.editor.setFont(theme.ui_font(points))
        self.editor.apply_column()

    def show_loading_text(self, text: str) -> None:
        self.skeleton.label.setText(text)
        self.pages.setCurrentWidget(self.skeleton)

    def show_error(self, message: str, action: str | None = None) -> None:
        self.banner.show_message(message, action)

    def hide_error(self) -> None:
        self.banner.hide()

    def set_progress(self, fraction: float | None) -> None:
        self.progress.setVisible(fraction is not None)
        if fraction is not None:
            self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))

    def set_drag_active(self, active: bool) -> None:
        self.setProperty("drag", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def displayed_text(self) -> str:
        return self.editor.toPlainText()

    # ---- final / progressive rendering ---------------------------------

    def clear(self) -> None:
        self._finish_fade()
        self.editor.clear()
        self._provisional_start = 0
        self._live_last = ""

    def render(self, segments: Sequence[Segment], timestamps: bool) -> None:
        self.clear()
        for segment in segments:
            self.append_segment(segment, timestamps)
        if not segments:
            self.show_empty()

    def append_segment(self, segment: Segment, timestamps: bool) -> None:
        self.pages.setCurrentWidget(self.editor)
        cursor = self._end_cursor()
        self._new_line(cursor)
        if timestamps:
            stamp = QTextCharFormat()
            stamp.setFont(theme.mono_font(10))
            stamp.setForeground(self._t.qcolor("muted"))
            cursor.insertText(f"{clock(segment.start)}   ", stamp)
        cursor.insertText(segment.text, QTextCharFormat())
        self._provisional_start = cursor.position()
        self._scroll_to_end()

    # ---- live rendering ------------------------------------------------

    def live_update(self, committed: Sequence[Segment], provisional: str) -> None:
        """Appends committed words and replaces the provisional tail."""
        self._finish_fade()
        self.pages.setCurrentWidget(self.editor)
        cursor = self.editor.textCursor()
        cursor.setPosition(self._provisional_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

        start = cursor.position()
        for segment in committed:
            for word in segment.words or (Word(segment.start, segment.end, " " + segment.text),):
                self._insert_live(cursor, word.text, self._fresh_format())
                self._live_last = word.text
        self._provisional_start = cursor.position()
        if committed and self._animate:
            self._fade_range = (start, self._provisional_start)
            self._fade.start()

        if provisional:
            fmt = QTextCharFormat()
            fmt.setForeground(self._t.qcolor("muted"))
            fmt.setFontItalic(True)
            self._insert_live(cursor, " " + provisional, fmt)
        self._scroll_to_end()

    def _fresh_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if self._animate:
            fmt.setForeground(self._t.qcolor("muted"))  # fades to the text colour
        return fmt

    def _insert_live(self, cursor: QTextCursor, word: str, fmt: QTextCharFormat) -> None:
        """Whisper words carry their leading space; a finished sentence starts a new line."""
        if not self._live_last:
            if cursor.position() == 0:
                cursor.setBlockFormat(self._block)
            cursor.insertText(word.lstrip(), fmt)
        elif self._live_last.rstrip().endswith(SENTENCE_END):
            cursor.insertBlock(self._block)
            cursor.insertText(word.lstrip(), fmt)
        else:
            cursor.insertText(word, fmt)

    # ---- helpers -------------------------------------------------------

    def _end_cursor(self) -> QTextCursor:
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        return cursor

    def _new_line(self, cursor: QTextCursor) -> None:
        if cursor.position() == 0:
            cursor.setBlockFormat(self._block)
        else:
            cursor.insertBlock(self._block)

    def _scroll_to_end(self) -> None:
        bar = self.editor.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _fade_step(self, value) -> None:
        start, end = self._fade_range
        if end <= start:
            return
        muted, text = self._t.qcolor("muted"), self._t.qcolor("text")
        v = float(value)
        color = muted
        color.setRedF(muted.redF() + (text.redF() - muted.redF()) * v)
        color.setGreenF(muted.greenF() + (text.greenF() - muted.greenF()) * v)
        color.setBlueF(muted.blueF() + (text.blueF() - muted.blueF()) * v)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(fmt)

    def _fade_done(self) -> None:
        start, end = self._fade_range
        if end > start:
            cursor = self.editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QTextCharFormat())  # back to the default text colour
        self._fade_range = (0, 0)

    def _finish_fade(self) -> None:
        if self._fade.state() == QVariantAnimation.State.Running:
            self._fade.stop()
            self._fade_done()
