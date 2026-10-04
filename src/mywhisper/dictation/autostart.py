"""Start with Windows: a value under the HKCU Run key, no admin rights needed."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "MyWhisper"


def command() -> str:
    """MyWhisper.exe --minimized, or pythonw.exe (no console) -m mywhisper from a checkout."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    return f'"{python}" -m mywhisper --minimized'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Returns False if the registry could not be written."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not update the Run registry key")
        return False
