"""Downloads and unpacks a GPU runtime: wheels are zip files, unpacking is enough."""

from __future__ import annotations

import logging
import shutil
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path

from mywhisper.download import DownloadCancelled, DownloadError, download_file, open_url
from mywhisper.runtime import store
from mywhisper.runtime.packages import RuntimePackage

log = logging.getLogger(__name__)

# (stage, done, total): stage is "download" or "extract", done/total in bytes
InstallProgress = Callable[[str, int, int], None]

__all__ = ["DownloadCancelled", "DownloadError", "free_space_ok", "install"]


def free_space_ok(package: RuntimePackage, root: Path | None = None) -> bool:
    root = root or store.runtime_root()
    probe = root
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free >= package.disk_needed


def install(
    package: RuntimePackage,
    root: Path | None = None,
    progress: InstallProgress | None = None,
    cancel: threading.Event | None = None,
    opener: Callable = open_url,
) -> Path:
    """Returns the install folder. Raises DownloadError (user message) or DownloadCancelled."""
    root = root or store.runtime_root()
    if not free_space_ok(package, root):
        needed = package.disk_needed / 1024**3
        raise DownloadError(f"Espace disque insuffisant : {needed:.0f} Go libres nécessaires sur {root.drive or root}.")
    downloads = root / "downloads"
    target = store.install_dir(package, root)
    staging = target.with_name(target.name + ".staging")

    received = 0

    def on_bytes(count: int) -> None:
        nonlocal received
        received += count
        if progress:
            progress("download", received, package.download_size)

    files = [
        download_file(d.url, downloads / d.filename, d.sha256, on_bytes, cancel, opener)
        for d in package.downloads
    ]

    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        wheels = [_wheel(path, d.member, staging) for path, d in zip(files, package.downloads, strict=True)]
        total = sum(_uncompressed(w) for w in wheels)
        done = 0
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as archive:
                for info in archive.infolist():
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    archive.extract(info, staging)
                    done += info.file_size
                    if progress:
                        progress("extract", done, total)
        for path in staging.glob("*.inner.whl"):
            path.unlink()
        store.write_manifest(staging, package)
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise DownloadError(f"Installation impossible : {exc}") from exc
    except DownloadCancelled:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(downloads, ignore_errors=True)
    log.info("Installed %s in %s", package.label, target)
    return target


def _wheel(path: Path, member: str | None, staging: Path) -> Path:
    """The wheel itself, or the wheel taken out of a release zip."""
    if member is None:
        return path
    inner = staging / (Path(member).stem + ".inner.whl")
    with zipfile.ZipFile(path) as archive, archive.open(member) as src, inner.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return inner


def _uncompressed(wheel: Path) -> int:
    with zipfile.ZipFile(wheel) as archive:
        return sum(info.file_size for info in archive.infolist()) or 1
