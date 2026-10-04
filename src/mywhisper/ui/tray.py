from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from mywhisper.ui import theme
from mywhisper.ui.theme import Tokens


class TrayIcon(QSystemTrayIcon):
    """Keeps MyWhisper (and its loaded model) alive in the background for the dictation."""

    open_requested = Signal()
    quit_requested = Signal()
    dictation_toggled = Signal(bool)

    def __init__(self, tokens: Tokens, hotkey_text: str, dictation_enabled: bool, parent=None) -> None:
        super().__init__(parent)
        self._t = tokens
        menu = QMenu()
        menu.addAction("Ouvrir MyWhisper", self.open_requested.emit)
        self.dictation_action = QAction("Dictée active", menu, checkable=True)
        self.dictation_action.setChecked(dictation_enabled)
        self.dictation_action.toggled.connect(self.dictation_toggled)
        menu.addAction(self.dictation_action)
        menu.addSeparator()
        menu.addAction("Quitter", self.quit_requested.emit)
        self._menu = menu  # the tray does not take ownership
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self.set_hotkey_text(hotkey_text)
        self.set_listening(False)

    def set_hotkey_text(self, hotkey_text: str) -> None:
        self.setToolTip(f"MyWhisper · dictée : {hotkey_text}")

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
