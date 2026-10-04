"""Running from the Microsoft Store package (MSIX) or from the classic installation.

Packaged, a few things behave differently:
- the package provides the Start menu entry: no .lnk is written (shortcuts.py);
- writes to HKCU are virtualized, so "start with Windows" is a StartupTask declared
  in the manifest (packaging/msix/AppxManifest.template.xml) instead of a Run value;
- new files under %LOCALAPPDATA% / %APPDATA% land in the package's own folder
  (...\\Packages\\<family name>\\LocalCache): Explorer, outside the package, must be
  given that real path (real_path).
"""

from __future__ import annotations

import ctypes
import functools
import os
import sys
from pathlib import Path

ERROR_INSUFFICIENT_BUFFER = 122


@functools.cache
def family_name() -> str | None:
    """The package family name, or None outside a package."""
    if sys.platform != "win32":
        return None
    length = ctypes.c_uint32(0)
    try:
        function = ctypes.windll.kernel32.GetCurrentPackageFamilyName
    except AttributeError:  # before Windows 8
        return None
    if function(ctypes.byref(length), None) != ERROR_INSUFFICIENT_BUFFER:
        return None  # APPMODEL_ERROR_NO_PACKAGE: not packaged
    buffer = ctypes.create_unicode_buffer(length.value)
    if function(ctypes.byref(length), buffer) != 0:
        return None
    return buffer.value


def is_packaged() -> bool:
    return family_name() is not None


def real_path(path: Path) -> Path:
    """Where a file under %LOCALAPPDATA% or %APPDATA% really is, as seen from outside
    the package. A folder that already existed before the package was installed is
    not redirected, so it is returned unchanged; same outside a package."""
    family = family_name()
    if family is None:
        return path
    redirected = _redirected(path, family)
    return redirected if redirected is not None and redirected.exists() else path


def _redirected(path: Path, family: str) -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    cache = Path(local) / "Packages" / family / "LocalCache"
    for variable, name in (("LOCALAPPDATA", "Local"), ("APPDATA", "Roaming")):
        base = os.environ.get(variable)
        if not base:
            continue
        try:
            relative = path.resolve().relative_to(Path(base).resolve())
        except ValueError:
            continue
        return cache / name / relative
    return None
