from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout

from doyoucopy.i18n import tr
from doyoucopy.ui import theme
from doyoucopy.ui.theme import Tokens


class NoticeBar(QFrame):
    """Informational banner (not an error): title, explanation, optional action."""

    action_clicked = Signal()

    def __init__(self, tokens: Tokens, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NoticeBar")
        self.icon = QLabel()
        self.icon.setFixedSize(20, 20)
        self.title = QLabel()
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.action = QPushButton()
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self.action_clicked)
        self.close_button = QToolButton()
        self.close_button.setObjectName("IconButton")
        self.close_button.setToolTip(tr("Masquer"))
        self.close_button.clicked.connect(self.hide)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.title)
        texts.addWidget(self.detail)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 8, 10)
        row.setSpacing(12)
        row.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, 1)
        row.addWidget(self.action, alignment=Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.set_tokens(tokens)
        self.hide()

    def set_tokens(self, tokens: Tokens) -> None:
        t = tokens
        self.setStyleSheet(
            f"#NoticeBar {{ background: {t.surface}; border: 1px solid {t.border}; "
            f"border-radius: {theme.RADIUS_CONTAINER}px; }}"
        )
        self.title.setStyleSheet(f"color: {t.text}; font-weight: 600;")
        self.detail.setStyleSheet(f"color: {t.muted};")
        self.icon.setPixmap(theme.icon("ph.cpu", t, "muted").pixmap(QSize(20, 20)))
        self.close_button.setIcon(theme.icon("ph.x", t, "muted"))

    def show_notice(self, title: str, detail: str, action: str | None = None) -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.action.setVisible(action is not None)
        if action:
            self.action.setText(action)
        self.show()
