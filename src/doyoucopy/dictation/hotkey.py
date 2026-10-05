"""System-wide dictation hotkey: a low-level keyboard hook (WH_KEYBOARD_LL).

RegisterHotKey would be simpler, but it only reports key presses: push-to-talk
needs the release too. The hook is installed from the Qt main thread, whose event
loop pumps the Win32 messages the hook relies on.

Windows silently removes a low-level hook whose callback once took too long
(LowLevelHooksTimeout, e.g. while the main thread was busy). Nothing reports it:
the hotkey would just stop working until a restart. The hook is therefore
reinstalled periodically, which costs two system calls.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence

from doyoucopy.dictation.inject import send_menu_mask
from doyoucopy.i18n import tr

log = logging.getLogger(__name__)

MOD_CTRL, MOD_SHIFT, MOD_ALT, MOD_WIN = 1, 2, 4, 8
VK_ESCAPE = 0x1B
REINSTALL_MS = 15_000  # longest time the hotkey may stay dead after Windows dropped the hook

_QT_MODIFIERS = (
    (Qt.KeyboardModifier.ControlModifier, MOD_CTRL),
    (Qt.KeyboardModifier.ShiftModifier, MOD_SHIFT),
    (Qt.KeyboardModifier.AltModifier, MOD_ALT),
    (Qt.KeyboardModifier.MetaModifier, MOD_WIN),
)
_NAMED_KEYS = {
    Qt.Key.Key_Space: 0x20,
    Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Delete: 0x2E,
    Qt.Key.Key_Home: 0x24,
    Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21,
    Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_Left: 0x25,
    Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27,
    Qt.Key.Key_Down: 0x28,
    Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_ScrollLock: 0x91,
}
# Keys that may be used alone: they do not type anything.
_STANDALONE = {0x13, 0x91, 0x2D} | set(range(0x70, 0x88))


@dataclass(frozen=True)
class Hotkey:
    vk: int
    mods: int
    text: str


def parse_hotkey(text: str) -> Hotkey:
    """'Ctrl+Shift+Space' -> Hotkey. Raises ValueError with a message for the user."""
    sequence = QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence.count() != 1:
        raise ValueError(tr("Raccourci invalide : « {hotkey} »").format(hotkey=text))
    combination = sequence[0]
    key = combination.key()
    modifiers = combination.keyboardModifiers()
    mods = 0
    for qt_modifier, flag in _QT_MODIFIERS:
        if modifiers & qt_modifier:
            mods |= flag
    vk = _vk(key)
    if vk is None:
        raise ValueError(tr("Touche non prise en charge dans « {hotkey} »").format(hotkey=text))
    if not mods and vk not in _STANDALONE:
        raise ValueError(tr("Ajoutez Ctrl, Alt, Maj ou Win : cette touche seule servirait à la frappe."))
    return Hotkey(vk, mods, sequence.toString(QKeySequence.SequenceFormat.PortableText))


def _vk(key: Qt.Key) -> int | None:
    value = int(key.value) if hasattr(key, "value") else int(key)
    if ord("A") <= value <= ord("Z") or ord("0") <= value <= ord("9"):
        return value
    f1 = int(Qt.Key.Key_F1.value)
    if f1 <= value <= f1 + 23:
        return 0x70 + value - f1
    for named, vk in _NAMED_KEYS.items():
        if int(named.value) == value:
            return vk
    return None


class HotkeyMatcher:
    """Pure state machine fed with raw key events; decides what to report and swallow."""

    def __init__(self, hotkey: Hotkey) -> None:
        self.hotkey = hotkey
        self.escape_armed = False  # Esc cancels, only while a dictation is running
        self._down = False

    @property
    def held(self) -> bool:
        """The hotkey is pressed: its release has not been seen yet."""
        return self._down

    def feed(self, vk: int, is_down: bool, mods: int) -> tuple[str | None, bool]:
        """Returns (event, swallow); event is "press", "release", "escape" or None."""
        if vk == self.hotkey.vk:
            if is_down:
                if self._down:
                    return None, True  # auto-repeat
                if mods == self.hotkey.mods:
                    self._down = True
                    return "press", True
                return None, False
            if self._down:
                self._down = False
                return "release", True
            return None, False
        if vk == VK_ESCAPE and is_down and self.escape_armed:
            return "escape", True
        return None, False


# ---- Win32 hook -----------------------------------------------------------

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_INJECTED = 0x10
_MODIFIER_KEYS = ((0x11, MOD_CTRL), (0x10, MOD_SHIFT), (0x12, MOD_ALT), (0x5B, MOD_WIN), (0x5C, MOD_WIN))


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


@lru_cache(maxsize=1)
def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return user32


def modifiers_down() -> int:
    if sys.platform != "win32":
        return 0
    user32 = _user32()
    mods = 0
    for vk, flag in _MODIFIER_KEYS:
        if user32.GetAsyncKeyState(vk) & 0x8000:
            mods |= flag
    return mods


class KeyboardHook(QObject):
    """Reports the dictation hotkey from anywhere in Windows."""

    pressed = Signal()
    released = Signal()
    escape = Signal()

    def __init__(self, parent: QObject | None = None, user32=None) -> None:
        super().__init__(parent)
        self._matcher: HotkeyMatcher | None = None
        self._handle = None
        self._proc = None  # keeps the ctypes callback alive
        self._suspended = False
        self._user32 = user32 or (_user32() if sys.platform == "win32" else None)
        self._signals = {"press": self.pressed, "release": self.released, "escape": self.escape}
        self._watchdog = QTimer(self, interval=REINSTALL_MS)
        self._watchdog.timeout.connect(self.reinstall)

    @property
    def hotkey(self) -> Hotkey | None:
        return self._matcher.hotkey if self._matcher else None

    def set_hotkey(self, hotkey: Hotkey) -> None:
        armed = self._matcher.escape_armed if self._matcher else False
        self._matcher = HotkeyMatcher(hotkey)
        self._matcher.escape_armed = armed

    def set_escape_armed(self, armed: bool) -> None:
        if self._matcher:
            self._matcher.escape_armed = armed

    def suspend(self) -> None:
        """While the user types a new shortcut in the settings."""
        self._suspended = True

    def resume(self) -> None:
        self._suspended = False

    def install(self) -> bool:
        if self._handle or self._user32 is None:
            return self._handle is not None
        self._proc = HOOKPROC(self._callback)
        self._handle = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._handle:
            log.error("SetWindowsHookExW failed: %s", ctypes.get_last_error())
            self._proc = None
            return False
        self._watchdog.start()
        return True

    def reinstall(self) -> None:
        """Puts a fresh hook in place of the current one (see the module docstring).

        The new hook is set before the old one is removed, so no key is missed; both
        calls run on this thread, which cannot run a hook callback in between. Skipped
        while the hotkey is held, so that its release reaches the same matcher state."""
        if not self._handle or self._user32 is None or (self._matcher and self._matcher.held):
            return
        handle = self._user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not handle:
            log.warning("Keyboard hook reinstall failed: %s", ctypes.get_last_error())
            return  # the current one may still be alive: keep it
        self._user32.UnhookWindowsHookEx(self._handle)  # fails harmlessly if Windows dropped it
        self._handle = handle

    def uninstall(self) -> None:
        self._watchdog.stop()
        if self._handle and self._user32:
            self._user32.UnhookWindowsHookEx(self._handle)
        self._handle = None
        self._proc = None

    def _callback(self, code: int, wparam: int, lparam: int) -> int:
        # Must return fast: Windows silently removes hooks that time out.
        try:
            if code == 0 and self._matcher and not self._suspended:
                info = KBDLLHOOKSTRUCT.from_address(lparam)
                if not info.flags & LLKHF_INJECTED:  # our own Ctrl+V and menu masks
                    is_down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                    if is_down or wparam in (WM_KEYUP, WM_SYSKEYUP):
                        event, swallow = self._matcher.feed(info.vkCode, is_down, modifiers_down())
                        if event:
                            # Slots run after the hook returns, never inside it.
                            QTimer.singleShot(0, self._signals[event].emit)
                            if event == "press" and self._matcher.hotkey.mods & (MOD_ALT | MOD_WIN):
                                # Releasing Alt/Win alone would then open the menu bar / Start menu.
                                QTimer.singleShot(0, send_menu_mask)
                        if swallow:
                            return 1
        except Exception:
            log.exception("Keyboard hook error")
        return self._user32.CallNextHookEx(None, code, wparam, lparam)
