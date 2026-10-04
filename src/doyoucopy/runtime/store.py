"""Where GPU runtimes live, and how one is put on the import path.

Packaged app (PyInstaller): CTranslate2 is deliberately left out of the frozen
archive and shipped as a plain folder (ct2_cpu, the PyPI build: CPU + CUDA). A
downloaded runtime is put in front of it on sys.path before ctranslate2 is first
imported:
- AMD: its own ROCm build of ctranslate2 shadows the bundled one;
- NVIDIA: the bundled build is kept, cuBLAS and cuDNN are added to the DLL search path.

From a source checkout (venv), nothing is touched: the venv's ctranslate2 is used.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

from doyoucopy.runtime.packages import RuntimePackage, python_tag

log = logging.getLogger(__name__)

MANIFEST = "runtime.json"
_dll_handles: list = []  # os.add_dll_directory handles must stay alive


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_root() -> Path:
    override = os.environ.get("DOYOUCOPY_RUNTIME_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "DoYouCopy" / "runtime"


def install_dir(package: RuntimePackage, root: Path | None = None) -> Path:
    return (root or runtime_root()) / f"{package.variant}-{python_tag()}"


def is_installed(package: RuntimePackage, root: Path | None = None) -> bool:
    try:
        data = json.loads((install_dir(package, root) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("version") == package.version and data.get("python") == python_tag()


def write_manifest(directory: Path, package: RuntimePackage) -> None:
    manifest = {"variant": package.variant, "version": package.version, "python": python_tag()}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def remove(package: RuntimePackage, root: Path | None = None) -> None:
    shutil.rmtree(install_dir(package, root), ignore_errors=True)


def bundled_ct2_dir() -> Path | None:
    if not is_frozen():
        return None
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "ct2_cpu"


def dll_dirs(package: RuntimePackage, root: Path | None = None) -> list[Path]:
    """Folders holding the runtime's DLLs (NVIDIA wheels put them in nvidia/*/bin)."""
    if package.variant != "nvidia":
        return []
    return sorted((install_dir(package, root) / "nvidia").glob("*/bin"))


def activate(package: RuntimePackage | None, root: Path | None = None) -> None:
    """Must run before the first `import ctranslate2`."""
    if package is not None:
        directory = install_dir(package, root)
        if package.variant == "amd":
            sys.path.insert(0, str(directory))
        for dll_dir in dll_dirs(package, root):
            _add_dll_dir(dll_dir)
    bundled = bundled_ct2_dir()
    if bundled is not None and str(bundled) not in sys.path:
        sys.path.append(str(bundled))


def _add_dll_dir(directory: Path) -> None:
    # cuDNN loads its sub-libraries with LoadLibrary: PATH covers that case too.
    os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
    if hasattr(os, "add_dll_directory"):
        try:
            _dll_handles.append(os.add_dll_directory(str(directory)))
        except OSError:
            log.warning("Could not add DLL directory %s", directory)
