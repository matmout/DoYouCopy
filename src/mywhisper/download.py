"""HTTP downloads with progress, cancellation, resume and SHA-256 check (stdlib only)."""

from __future__ import annotations

import hashlib
import http.client
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from mywhisper import __version__

CHUNK = 1024 * 1024
TIMEOUT_S = 60
USER_AGENT = f"MyWhisper/{__version__}"

Progress = Callable[[int], None]  # bytes received since the previous call


class DownloadCancelled(Exception):
    pass


class DownloadError(Exception):
    """Message meant for the user."""


def open_url(url: str, offset: int = 0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(
    url: str,
    dest: Path,
    sha256: str | None = None,
    progress: Progress | None = None,
    cancel: threading.Event | None = None,
    opener: Callable = open_url,
) -> Path:
    """Downloads url to dest through dest.part, resuming a previous partial download.

    progress also receives the bytes already present when resuming, so a caller can
    add everything up against the expected total.

    Raises DownloadError (message for the user) or DownloadCancelled. dest only ever
    appears complete: the data goes to dest.part, renamed once the SHA-256 matches.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha256 is None or file_sha256(dest) == sha256):
        if progress:
            progress(dest.stat().st_size)
        return dest
    part = dest.with_name(dest.name + ".part")
    offset = part.stat().st_size if part.exists() else 0
    digest = hashlib.sha256()
    try:
        response = opener(url, offset)
    except urllib.error.HTTPError as exc:
        if exc.code != 416 or not offset:
            raise DownloadError(f"Téléchargement impossible ({_host(url)}) : {exc}") from exc
        # 416 Range Not Satisfiable: the .part is already whole (or longer than the file,
        # if it changed on the server). Without starting over, every retry would fail.
        part.unlink(missing_ok=True)
        return download_file(url, dest, sha256, progress, cancel, opener)
    except OSError as exc:
        raise DownloadError(f"Téléchargement impossible ({_host(url)}) : {exc}") from exc
    with response:
        resumed = offset and getattr(response, "status", 200) == 206
        if resumed:
            with part.open("rb") as f:
                for block in iter(lambda: f.read(CHUNK), b""):
                    digest.update(block)
            if progress:
                progress(offset)
        mode = "ab" if resumed else "wb"
        try:
            with part.open(mode) as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    block = response.read(CHUNK)
                    if not block:
                        break
                    f.write(block)
                    digest.update(block)
                    if progress:
                        progress(len(block))
        except (OSError, http.client.HTTPException) as exc:  # IncompleteRead is not an OSError
            raise DownloadError(f"Téléchargement interrompu ({_host(url)}) : {exc}") from exc
    if sha256 is not None and digest.hexdigest() != sha256:
        part.unlink(missing_ok=True)
        raise DownloadError(f"Fichier corrompu ou modifié : {dest.name} (empreinte SHA-256 incorrecte)")
    part.replace(dest)
    return dest


def _host(url: str) -> str:
    return url.split("/")[2] if "://" in url else url
