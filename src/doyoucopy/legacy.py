"""Data left by MyWhisper, the app's former name, moved once to the DoYouCopy folders.

Runs at every start (it does nothing once the old folders are gone) and from the
installer (--migrate), before the old version is uninstalled: the models, the history,
the settings and the GPU runtime are kept instead of being downloaded or lost.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

LEGACY_NAME = "MyWhisper"
NAME = "DoYouCopy"


def _base(env_var: str, fallback: str) -> Path:
    return Path(os.environ.get(env_var) or str(Path.home() / "AppData" / fallback))


def migrate() -> list[str]:
    """Moves what MyWhisper left, item by item (an item already in the new folder is
    kept as is). Returns what was moved, for the log, which is not set up yet."""
    moved: list[str] = []
    for env_var, fallback in (("LOCALAPPDATA", "Local"), ("APPDATA", "Roaming")):
        old, new = _base(env_var, fallback) / LEGACY_NAME, _base(env_var, fallback) / NAME
        if not old.is_dir():
            continue
        new.mkdir(parents=True, exist_ok=True)
        for child in old.iterdir():
            target = new / child.name
            if target.exists():
                continue
            try:
                os.replace(child, target)
                moved.append(str(target))
            except OSError:
                pass  # in use (the old app still running): tried again at the next start
        try:
            old.rmdir()
        except OSError:
            pass  # something could not move
    _fix_models_dir()
    _move_autostart()
    return moved


def _fix_models_dir() -> None:
    """settings.json stores the models folder as an absolute path: follow the move."""
    path = _base("APPDATA", "Roaming") / NAME / "settings.json"
    old = str(_base("LOCALAPPDATA", "Local") / LEGACY_NAME)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        models_dir = data.get("models_dir")
        if not isinstance(models_dir, str) or not models_dir.lower().startswith(old.lower()):
            return
        data["models_dir"] = str(_base("LOCALAPPDATA", "Local") / NAME) + models_dir[len(old):]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError, AttributeError):
        pass


def _move_autostart() -> None:
    """"Start with Windows" was a Run value named MyWhisper: replace it with ours."""
    if sys.platform != "win32":
        return
    import winreg

    from doyoucopy.dictation import autostart

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            winreg.QueryValueEx(key, LEGACY_NAME)
            winreg.DeleteValue(key, LEGACY_NAME)
    except OSError:
        return  # no old value
    autostart.set_enabled(True)
