"""First-launch model download with a real progress bar.

huggingface_hub reports no usable byte progress, so the files are fetched directly
from the Hub (HTTP, with resume) into a plain folder that faster-whisper loads as is.
The Hub's tree API gives each file's size and, for LFS files such as model.bin,
its SHA-256.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mywhisper.download import DownloadError, download_file, open_url

HUB = "https://huggingface.co"
# The files faster-whisper needs (faster_whisper.utils.download_model).
PATTERNS = ("config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*")
COMPLETE = ".complete"

ModelProgress = Callable[[int, int], None]  # done, total bytes


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    sha256: str | None


def repo_id(model_name: str) -> str:
    from faster_whisper.utils import _MODELS

    return _MODELS.get(model_name, model_name)


def local_dir(models_dir: Path, model_name: str) -> Path:
    return models_dir / model_name


def is_complete(directory: Path) -> bool:
    return (directory / COMPLETE).exists() and (directory / "model.bin").exists()


def list_files(repo: str, opener: Callable = open_url) -> list[RemoteFile]:
    try:
        with opener(f"{HUB}/api/models/{repo}/tree/main") as response:
            entries = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise DownloadError(f"Impossible de joindre huggingface.co : {exc}") from exc
    files = []
    for entry in entries:
        path = entry.get("path", "")
        if entry.get("type") == "file" and any(fnmatch.fnmatch(path, p) for p in PATTERNS):
            lfs = entry.get("lfs") or {}
            files.append(RemoteFile(path, int(lfs.get("size") or entry.get("size") or 0), lfs.get("oid")))
    if not any(f.path == "model.bin" for f in files):
        raise DownloadError(f"Modèle introuvable sur huggingface.co : {repo}")
    return files


def download(
    model_name: str,
    models_dir: Path,
    progress: ModelProgress | None = None,
    cancel: threading.Event | None = None,
    opener: Callable = open_url,
) -> Path:
    repo = repo_id(model_name)
    target = local_dir(models_dir, model_name)
    if is_complete(target):
        return target
    files = list_files(repo, opener)
    total = sum(f.size for f in files)
    done = 0

    def on_bytes(count: int) -> None:
        nonlocal done
        done += count
        if progress:
            progress(min(done, total), total)

    for remote in files:
        download_file(
            f"{HUB}/{repo}/resolve/main/{remote.path}", target / remote.path, remote.sha256, on_bytes, cancel, opener
        )
    (target / COMPLETE).write_text(repo, encoding="utf-8")
    return target


def discard(models_dir: Path, model_name: str) -> None:
    shutil.rmtree(local_dir(models_dir, model_name), ignore_errors=True)
