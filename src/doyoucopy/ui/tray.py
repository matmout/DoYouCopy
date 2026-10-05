"""Notification-area icon: keeps the app (and its model) running for the dictation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from doyoucopy.i18n import tr
from doyoucopy.ui import theme
from doyoucopy.ui.theme import Tokens


class TrayIcon(QSystemTrayIcon):
    """Keeps DoYouCopy (and its loaded model) alive in the background for the dictation."""

    open_requested = Signal()
    quit_requested = Signal()
    dictation_toggled = Signal(bool)

    def __init__(self, tokens: Tokens, hotkey_text: str, dictation_enabled: bool, parent=None) -> None:
        super().__init__(parent)
        self._t = tokens
        menu = QMenu()
        menu.addAction(tr("Ouvrir DoYouCopy"), self.open_requested.emit)
        self.dictation_action = QAction(tr("Dictée active"), menu, checkable=True)
        self.dictation_action.setChecked(dictation_enabled)
        self.dictation_action.toggled.connect(self.dictation_toggled)
        menu.addAction(self.dictation_action)
        menu.addSeparator()
        menu.addAction(tr("Quitter"), self.quit_requested.emit)
        self._menu = menu  # the tray does not take ownership
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.set_hotkey_text(hotkey_text)
        self.set_listening(False)

    def set_hotkey_text(self, hotkey_text: str) -> None:
        self.setToolTip(tr("DoYouCopy · dictée : {hotkey}").format(hotkey=hotkey_text))

    def set_tokens(self, tokens: Tokens) -> None:
        self._t = tokens
        self.set_listening(self._listening)

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        name = "ph.microphone-fill" if listening else "ph.microphone"
        self.setIcon(theme.icon(name, self._t, "accent"))  # readable on light and dark taskbars

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_requested.emit()
