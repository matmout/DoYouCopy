"""Shortcuts to DoYouCopy on the Desktop and in the Start menu.

The installer offers both (installer/doyoucopy.iss, [Tasks]); the settings window
can add or remove them later. Both write the same files, so each sees the other's:
- Desktop:    <user Desktop>\\DoYouCopy.lnk
- Start menu: <user Start menu>\\Programs\\DoYouCopy\\DoYouCopy.lnk
(per-user install: the installer's {userdesktop} and {group} are these folders).

Each shortcut carries the app's AppUserModelID, the identity the running app takes
(app.set_app_user_model_id): a shortcut pinned to the taskbar then groups with the
window instead of showing a second icon. A .lnk is written through the Shell's own
COM objects (IShellLink, IPropertyStore, IPersistFile), as the installer does.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import POINTER, byref, c_void_p, wintypes
from dataclasses import dataclass
from pathlib import Path

from doyoucopy.i18n import N_, tr

log = logging.getLogger(__name__)

APP_ID = "DoYouCopy.DoYouCopy"  # same value in app.py and installer/doyoucopy.iss
NAME = "DoYouCopy"
DESCRIPTION = N_("Transcription vocale locale")
DESKTOP, START_MENU = "desktop", "start_menu"

CSIDL_PROGRAMS = 0x02  # <user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs
CSIDL_DESKTOPDIRECTORY = 0x10

CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"
IID_IPropertyStore = "{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}"
PKEY_AppUserModel_ID = ("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}", 5)
VT_LPWSTR = 31
MAX_PATH = 260

# vtable indices, in the order of ShObjIdl_core.h / PropSys.h / ObjIdl.h
LINK_GET_PATH, LINK_SET_DESCRIPTION, LINK_SET_WORKING_DIR = 3, 7, 9
LINK_GET_ARGUMENTS, LINK_SET_ARGUMENTS, LINK_SET_ICON, LINK_SET_PATH = 10, 11, 17, 20
STORE_GET_VALUE, STORE_SET_VALUE, STORE_COMMIT = 5, 6, 7
FILE_LOAD, FILE_SAVE = 5, 6


@dataclass(frozen=True)
class Target:
    """What a shortcut (or the Run key of autostart.py) launches."""

    program: Path
    arguments: str = ""
    icon: Path | None = None  # None: the program's own icon

    def command_line(self, extra: str = "") -> str:
        arguments = " ".join(a for a in (self.arguments, extra) if a)
        return f'"{self.program}" {arguments}'.rstrip()


def launch_target(with_icon: bool = False) -> Target:
    """DoYouCopy.exe when installed; from a source checkout, pythonw.exe (no console)
    -m doyoucopy. with_icon: from a checkout, an .ico is drawn for the shortcut
    (it would show python's icon otherwise)."""
    if getattr(sys, "frozen", False):
        return Target(Path(sys.executable))
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    icon = _checkout_icon() if with_icon else None
    return Target(pythonw if pythonw.exists() else python, "-m doyoucopy", icon)


def _checkout_icon() -> Path | None:
    """%LOCALAPPDATA%\\DoYouCopy\\doyoucopy.ico, written once (needs a QGuiApplication)."""
    from doyoucopy.config import _app_dir

    path = _app_dir("LOCALAPPDATA", "Local") / "doyoucopy.ico"
    if path.is_file():
        return path
    try:
        from doyoucopy.ui.app_icon import write_ico

        return write_ico(path)
    except Exception:
        log.exception("Could not write the shortcut icon")
        return None


# ---- locations ------------------------------------------------------------------


def _shell_folder(csidl: int) -> Path:
    buffer = ctypes.create_unicode_buffer(MAX_PATH)
    ctypes.OleDLL("shell32").SHGetFolderPathW(None, csidl, None, 0, buffer)
    return Path(buffer.value)


def location(kind: str) -> Path:
    """Where the shortcut of that kind lives (whether it exists or not)."""
    if kind == DESKTOP:
        return _shell_folder(CSIDL_DESKTOPDIRECTORY) / f"{NAME}.lnk"
    if kind == START_MENU:
        return _shell_folder(CSIDL_PROGRAMS) / NAME / f"{NAME}.lnk"
    raise ValueError(kind)


def available() -> bool:
    """No .lnk from the Microsoft Store package: it has its own Start menu entry, and
    its program path changes with every update."""
    from doyoucopy.desktop import packaging

    return sys.platform == "win32" and not packaging.is_packaged()


def exists(kind: str) -> bool:
    return available() and location(kind).is_file()


def set_enabled(kind: str, enabled: bool) -> bool:
    """Creates or removes the shortcut. False (and logged) if it could not be done."""
    if not available():
        return False
    path = location(kind)
    try:
        if enabled:
            create(path, launch_target(with_icon=True))
        else:
            remove(path)
    except OSError:
        log.exception("Could not %s the %s shortcut", "create" if enabled else "remove", kind)
        return False
    return True


def remove(path: Path) -> None:
    """Deletes the shortcut, and the Start menu folder if nothing else is left in it
    (it also holds the uninstaller's shortcut after an installation)."""
    path.unlink(missing_ok=True)
    if path.parent.name == NAME:
        try:
            path.parent.rmdir()
        except OSError:
            pass  # not empty


# ---- .lnk files -------------------------------------------------------------------


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    # vt, three reserved words, then a union whose largest member is two pointers
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("value", c_void_p),
        ("extra", c_void_p),
    ]


def _app_id_key() -> PROPERTYKEY:
    import uuid

    fmtid, pid = PKEY_AppUserModel_ID
    key = PROPERTYKEY(pid=pid)
    ctypes.memmove(key.fmtid, uuid.UUID(fmtid).bytes_le, 16)
    return key


def create(path: Path, target: Target, app_id: str = APP_ID) -> None:
    """Writes path (.lnk) launching target. Raises OSError on failure."""
    from doyoucopy.desktop import com

    path.parent.mkdir(parents=True, exist_ok=True)
    text = (ctypes.c_wchar_p,)
    with com.apartment():
        link = com.create(CLSID_ShellLink, IID_IShellLinkW)
        store = persist = None
        try:
            link.call(LINK_SET_PATH, str(target.program), argtypes=text)
            link.call(LINK_SET_ARGUMENTS, target.arguments, argtypes=text)
            link.call(LINK_SET_WORKING_DIR, str(target.program.parent), argtypes=text)
            link.call(LINK_SET_DESCRIPTION, tr(DESCRIPTION), argtypes=text)
            icon = target.icon or target.program
            link.call(LINK_SET_ICON, str(icon), 0, argtypes=(ctypes.c_wchar_p, ctypes.c_int))
            store = link.query(IID_IPropertyStore)
            value = ctypes.create_unicode_buffer(app_id)  # copied by SetValue
            variant = PROPVARIANT(vt=VT_LPWSTR, value=ctypes.cast(value, c_void_p))
            store.call(STORE_SET_VALUE, byref(_app_id_key()), byref(variant),
                       argtypes=(POINTER(PROPERTYKEY), POINTER(PROPVARIANT)))
            store.call(STORE_COMMIT)
            persist = link.query(IID_IPersistFile)
            persist.call(FILE_SAVE, str(path), True, argtypes=(ctypes.c_wchar_p, wintypes.BOOL))
        finally:
            for item in (persist, store, link):
                if item is not None:
                    item.release()


@dataclass(frozen=True)
class ShortcutInfo:
    program: str
    arguments: str
    app_id: str | None


def read(path: Path) -> ShortcutInfo:
    """What a .lnk launches, and its AppUserModelID (for checks and tests)."""
    from doyoucopy.desktop import com

    with com.apartment():
        link = com.create(CLSID_ShellLink, IID_IShellLinkW)
        store = persist = None
        try:
            persist = link.query(IID_IPersistFile)
            persist.call(FILE_LOAD, str(path), 0, argtypes=(ctypes.c_wchar_p, wintypes.DWORD))
            program = ctypes.create_unicode_buffer(32768)
            link.call(LINK_GET_PATH, program, len(program), None, 0,
                      argtypes=(ctypes.c_wchar_p, ctypes.c_int, c_void_p, wintypes.DWORD))
            arguments = ctypes.create_unicode_buffer(32768)
            link.call(LINK_GET_ARGUMENTS, arguments, len(arguments), argtypes=(ctypes.c_wchar_p, ctypes.c_int))
            store = link.query(IID_IPropertyStore)
            variant = PROPVARIANT()
            store.call(STORE_GET_VALUE, byref(_app_id_key()), byref(variant),
                       argtypes=(POINTER(PROPERTYKEY), POINTER(PROPVARIANT)))
            app_id = ctypes.wstring_at(variant.value) if variant.vt == VT_LPWSTR and variant.value else None
            ctypes.OleDLL("ole32").PropVariantClear(byref(variant))
            return ShortcutInfo(program.value, arguments.value, app_id)
        finally:
            for item in (persist, store, link):
                if item is not None:
                    item.release()


def describe(kind: str) -> str:
    """Folder shown to the user next to the checkbox."""
    return os.path.normpath(location(kind).parent) if available() else ""
