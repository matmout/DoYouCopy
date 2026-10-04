"""Puts the dictated text into the application that has the focus.

Pasting (clipboard + Ctrl+V) is more reliable than typing characters one by one:
accents, emojis and long texts arrive in one go. The previous clipboard is restored.

Known limit: Windows silently drops SendInput aimed at a window that runs as
administrator (UIPI). The "clipboard" output mode is the fallback.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from functools import lru_cache

from PySide6.QtCore import QMimeData, QObject, QTimer
from PySide6.QtGui import QGuiApplication

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL, VK_V = 0x11, 0x56
VK_MASK = 0xE8  # unassigned: cancels the menu that a lone Alt/Win release would open
_MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, left/right Win

RESTORE_DELAY_MS = 400  # time for the target app to read the clipboard
RELEASE_POLL_MS = 20
RELEASE_TIMEOUT_MS = 1000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]  # the mouse member sets the size


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


@lru_cache(maxsize=1)
def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    return user32


def _send_keys(*keys: tuple[int, bool]) -> bool:
    """keys: (virtual key, is_down) pairs, sent as one atomic batch."""
    if sys.platform != "win32":
        return False
    inputs = (INPUT * len(keys))()
    for item, (vk, down) in zip(inputs, keys, strict=True):
        item.type = INPUT_KEYBOARD
        item.u.ki = KEYBDINPUT(vk, 0, 0 if down else KEYEVENTF_KEYUP, 0, 0)
    sent = _user32().SendInput(len(keys), inputs, ctypes.sizeof(INPUT))
    if sent != len(keys):
        log.warning("SendInput sent %d/%d events (error %s)", sent, len(keys), ctypes.get_last_error())
    return sent == len(keys)


def send_ctrl_v() -> bool:
    return _send_keys((VK_CONTROL, True), (VK_V, True), (VK_V, False), (VK_CONTROL, False))


def send_menu_mask() -> None:
    _send_keys((VK_MASK, True), (VK_MASK, False))


def any_modifier_down() -> bool:
    if sys.platform != "win32":
        return False
    return any(_user32().GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIERS)


def foreground_is_own_process() -> bool:
    """True when a DoYouCopy window has the focus: pasting there makes no sense."""
    if sys.platform != "win32":
        return False
    user32 = _user32()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


def _copy_mime(source: QMimeData | None) -> QMimeData | None:
    if source is None or not source.formats():
        return None
    copy = QMimeData()
    for fmt in source.formats():
        copy.setData(fmt, source.data(fmt))
    return copy


class Paster(QObject):
    """Clipboard + Ctrl+V into the focused window, then restores the clipboard."""

    def copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def paste(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        saved = _copy_mime(clipboard.mimeData())
        clipboard.setText(text)
        self._wait_then_paste(text, saved, RELEASE_TIMEOUT_MS)

    def _wait_then_paste(self, text: str, saved: QMimeData | None, remaining_ms: int) -> None:
        # Ctrl+V with Shift or Alt still held would become another shortcut.
        if any_modifier_down() and remaining_ms > 0:
            QTimer.singleShot(
                RELEASE_POLL_MS, lambda: self._wait_then_paste(text, saved, remaining_ms - RELEASE_POLL_MS)
            )
            return
        send_ctrl_v()
        QTimer.singleShot(RESTORE_DELAY_MS, lambda: self._restore(text, saved))

    def _restore(self, text: str, saved: QMimeData | None) -> None:
        clipboard = QGuiApplication.clipboard()
        if saved is not None and clipboard.text() == text:  # untouched since the paste
            clipboard.setMimeData(saved)
