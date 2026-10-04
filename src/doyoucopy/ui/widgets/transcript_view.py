from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QKeySequence, QLinearGradient, QPainter, QTextBlockFormat, QTextCharFormat, QTextCursor
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

from doyoucopy.core.live import SENTENCE_END
from doyoucopy.core.types import Segment, Word
from doyoucopy.session import clock
from doyoucopy.ui import theme
from doyoucopy.ui.theme import Tokens

READY = (
    "Prêt à transcrire",
    "Cliquez sur le micro ou appuyez sur Ctrl+R.\nVous pouvez aussi déposer un fichier audio ici.",
)
LISTENING_RECORD = ("À l'écoute", "Cliquez à nouveau sur le bouton pour arrêter et transcrire.")
LISTENING_LIVE = ("À l'écoute", "Le texte apparaîtra dès les premiers mots.")
READING_CHARS = 72
LINE_HEIGHT = 155  # percent
LOW_CONFIDENCE = 0.5  # words below are underlined: probable errors
LINE_SEPARATOR = "\u2028"  # a line break inside a block: one block per segment, always


@dataclass(frozen=True)
class _Span:
    """Where a timed word (or a whole segment without words) sits in the document."""

    start: float
    end: float
    first: int  # document positions
    last: int


class _ReadingEdit(QTextEdit):
    """Text centred in a column of ~72 characters, the comfortable reading width.

    Read-only, except in edit mode where each block stays one segment: no new line,
    no merge of two lines.
    """

    clicked = Signal(int)  # document position of a plain click (no selection)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptRichText(False)
        self.setFont(theme.ui_font(12))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.set_editable(False)
        self._press = None

    def set_editable(self, editable: bool) -> None:
        self.setReadOnly(not editable)
        if editable:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        else:
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )

    def mousePressEvent(self, event) -> None:
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        point = event.position().toPoint()
        if (
            self.isReadOnly()
            and event.button() == Qt.MouseButton.LeftButton
            and self._press is not None
            and (point - self._press).manhattanLength() < 4
            and not self.textCursor().hasSelection()
        ):
            self.clicked.emit(self.cursorForPosition(point).position())
        self._press = None

    def keyPressEvent(self, event) -> None:
        if not self.isReadOnly() and self._breaks_segments(event):
            return
        super().keyPressEvent(event)

    def _breaks_segments(self, event) -> bool:
        cursor = self.textCursor()
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return True
        if cursor.hasSelection():
            first = self.document().findBlock(cursor.selectionStart())
            last = self.document().findBlock(cursor.selectionEnd())
            edits = bool(event.text()) or key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) or event.matches(
                QKeySequence.StandardKey.Cut
            ) or event.matches(QKeySequence.StandardKey.Paste)
            return first != last and edits
        if key == Qt.Key.Key_Backspace:
            return cursor.atBlockStart()
        if key == Qt.Key.Key_Delete:
            return cursor.atBlockEnd()
        return False

    def insertFromMimeData(self, source) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection() and (
            self.document().findBlock(cursor.selectionStart()) != self.document().findBlock(cursor.selectionEnd())
        ):
            return
        cursor.insertText(" ".join(source.text().split()))

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
    word_clicked = Signal(float)  # seconds: a click on a timed word

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
        self.editor.clicked.connect(self._on_click)
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
        self._spans: list[_Span] = []
        self._span_starts: list[float] = []
        self._highlighted: _Span | None = None
        self.editing = False
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
        self._spans = []
        self._span_starts = []
        self._highlighted = None
        self.editor.setExtraSelections([])

    def render(self, segments: Sequence[Segment], timestamps: bool, scroll: bool = True) -> None:
        """One block per segment, in order: block n is segment n."""
        bar = self.editor.verticalScrollBar()
        position = bar.value()
        self.clear()
        for segment in segments:
            self.append_segment(segment, timestamps, scroll=False)
        if not segments:
            self.show_empty()
        if scroll:
            self._scroll_to_end()
        else:
            bar.setValue(position)

    def append_segment(self, segment: Segment, timestamps: bool, scroll: bool = True) -> None:
        self.pages.setCurrentWidget(self.editor)
        cursor = self._end_cursor()
        self._new_line(cursor)
        if timestamps and not self.editing:
            stamp = QTextCharFormat()
            stamp.setFont(theme.mono_font(10))
            stamp.setForeground(self._t.qcolor("muted"))
            cursor.insertText(f"{clock(segment.start)}   ", stamp)
        text_start = cursor.position()
        cursor.insertText(segment.text.replace("\n", LINE_SEPARATOR), QTextCharFormat())
        self._provisional_start = cursor.position()
        self._add_spans(segment, text_start)
        if scroll:
            self._scroll_to_end()

    def _add_spans(self, segment: Segment, text_start: int) -> None:
        """Finds each word in the segment text (replacements may have changed some: those
        are skipped) and underlines the doubtful ones."""
        spans, offset = [], 0
        for word in segment.words:
            token = word.text.strip()
            index = segment.text.find(token, offset) if token else -1
            if index < 0:
                continue
            offset = index + len(token)
            spans.append(_Span(word.start, word.end, text_start + index, text_start + offset))
            if word.probability is not None and word.probability < LOW_CONFIDENCE and not self.editing:
                self._underline(text_start + index, text_start + offset)
        if not spans:
            spans.append(_Span(segment.start, segment.end, text_start, text_start + len(segment.text)))
        for span in spans:
            index = bisect.bisect_right(self._span_starts, span.start)
            self._span_starts.insert(index, span.start)
            self._spans.insert(index, span)

    def _underline(self, first: int, last: int) -> None:
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        fmt.setUnderlineColor(self._t.qcolor("accent", 0.7))
        fmt.setToolTip("Mot incertain : à vérifier")
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(first)
        cursor.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(fmt)

    # ---- audio synchronisation -------------------------------------------

    def span_at_time(self, seconds: float) -> _Span | None:
        index = bisect.bisect_right(self._span_starts, seconds) - 1
        if index < 0:
            return None
        span = self._spans[index]
        return span if seconds < span.end + 0.3 else None  # keeps the word lit through short gaps

    def highlight_time(self, seconds: float) -> None:
        """Lights the word spoken at this instant and keeps it in view."""
        if self.editing:
            return
        span = self.span_at_time(seconds)
        if span == self._highlighted:
            return
        self._highlighted = span
        if span is None:
            self.editor.setExtraSelections([])
            return
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._t.qcolor("accent", 0.25))
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(span.first)
        cursor.setPosition(span.last, QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = cursor
        self.editor.setExtraSelections([selection])
        rect = self.editor.cursorRect(cursor)
        viewport = self.editor.viewport().rect()
        if not viewport.adjusted(0, 40, 0, -40).contains(rect):
            bar = self.editor.verticalScrollBar()
            bar.setValue(bar.value() + rect.center().y() - viewport.height() // 3)

    def clear_highlight(self) -> None:
        self._highlighted = None
        self.editor.setExtraSelections([])

    def _on_click(self, position: int) -> None:
        for span in self._spans:
            if span.first <= position <= span.last:
                self.word_clicked.emit(span.start)
                return

    # ---- correction ----------------------------------------------------

    def start_editing(self, segments: Sequence[Segment]) -> None:
        """Edit mode: plain text, one line per segment, timestamps and underlines hidden."""
        self.editing = True
        self.clear_highlight()
        self.render(segments, timestamps=False, scroll=False)
        self.editor.set_editable(True)
        self.editor.setFocus()

    def stop_editing(self) -> list[str]:
        """Leaves edit mode and returns the text of each segment; the caller renders again."""
        texts = self.edited_texts()
        self.editing = False
        self.editor.set_editable(False)
        return texts

    def edited_texts(self) -> list[str]:
        document = self.editor.document()
        return [
            document.findBlockByNumber(n).text().replace(LINE_SEPARATOR, "\n")
            for n in range(document.blockCount())
        ]

    def selected_segments(self) -> tuple[int, int] | None:
        """Block numbers (= segment indexes) covered by the selection, or under the cursor."""
        if self.pages.currentWidget() is not self.editor or not self._spans:
            return None
        cursor = self.editor.textCursor()
        document = self.editor.document()
        first = document.findBlock(cursor.selectionStart()).blockNumber()
        last = document.findBlock(cursor.selectionEnd()).blockNumber()
        return first, last

    # ---- live rendering ------------------------------------------------

    def live_update(self, committed: Sequence[Segment], provisional: str) -> None:
        """Appends committed words and replaces the provisional tail."""
        self._finish_fade()
        self._spans, self._span_starts = [], []  # live text is not one block per segment
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
