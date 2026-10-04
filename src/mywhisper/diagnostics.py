"""Log files and the « diagnostic information » report users paste into a bug report.

The report describes the machine and the configuration, never the user's content:
no transcript, no vocabulary, no context prompt, no file names.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mywhisper import __version__
from mywhisper.config import Settings

log = logging.getLogger(__name__)

LOG_NAME = "mywhisper.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
PACKAGES = ("faster-whisper", "ctranslate2", "PySide6", "av", "numpy", "sounddevice", "onnxruntime")
# settings left out of the report: they may hold personal words or names
PRIVATE_SETTINGS = {"hotwords", "replacements", "initial_prompt", "input_device", "models_dir"}
RECENT_ISSUES = 40


def default_logs_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "MyWhisper" / "logs"


def setup_logging(logs_dir: Path | None = None, console: bool = True) -> Path | None:
    """Logs to a rotating file (always) and to the console (source checkout).

    Uncaught exceptions, in Qt slots and in threads, end up in the log too.
    Returns the log file, or None if it cannot be written.
    """
    handlers: list[logging.Handler] = []
    if console and sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    path: Path | None = (logs_dir or default_logs_dir()) / LOG_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8"))
    except OSError:
        path = None
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers, force=True)
    install_excepthooks()
    return path


def install_excepthooks() -> None:
    previous = sys.excepthook

    def excepthook(kind, value, traceback) -> None:
        logging.getLogger("mywhisper").critical("Uncaught exception", exc_info=(kind, value, traceback))
        if previous not in (None, sys.__excepthook__):
            previous(kind, value, traceback)

    def thread_excepthook(args) -> None:
        logging.getLogger("mywhisper").critical(
            "Uncaught exception in thread %s", args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook


def recent_issues(log_file: Path, limit: int = RECENT_ISSUES) -> list[str]:
    """The last warnings and errors of the log, with their tracebacks."""
    lines: deque[str] = deque(maxlen=limit)
    keep = False
    try:
        with open(log_file, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if line[:4].isdigit():  # a new record: "2026-10-04 12:00:00,123 LEVEL name: …"
                    parts = line.split(" ", 3)
                    keep = len(parts) > 2 and parts[2] in ("WARNING", "ERROR", "CRITICAL")
                if keep:
                    lines.append(line)
    except OSError:
        return []
    return list(lines)


def package_versions() -> dict[str, str]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "absent"
    return versions


@dataclass
class Context:
    """What the running app knows, gathered by the main window."""

    settings: Settings
    device_description: str = ""
    runtime_variant: str | None = None
    cpu_notice: str | None = None  # why the CPU is used, if it is
    model_loaded: str | None = None
    microphones: list[str] = field(default_factory=list)
    history_count: int | None = None
    log_file: Path | None = None
    adapters: Callable[[], list] | None = None  # gpu_detect.list_adapters (slow: PowerShell)


def _gpu_lines() -> list[str]:
    try:
        import ctranslate2
    except Exception as exc:  # the runtime DLLs may be the very problem
        return [f"CTranslate2 : import impossible ({exc})"]
    lines = []
    try:
        count = ctranslate2.get_cuda_device_count()
        lines.append(f"Cartes vues par CTranslate2 : {count}")
        if count:
            lines.append("Précisions GPU : " + ", ".join(sorted(ctranslate2.get_supported_compute_types("cuda"))))
    except Exception as exc:
        lines.append(f"Cartes vues par CTranslate2 : erreur ({exc})")
    try:
        lines.append("Précisions CPU : " + ", ".join(sorted(ctranslate2.get_supported_compute_types("cpu"))))
    except Exception:
        pass
    return lines


def _models_lines(settings: Settings) -> list[str]:
    from mywhisper.core import model_download
    from mywhisper.core.models import MODELS

    lines = []
    for spec in MODELS.values():
        try:
            size = model_download.installed_size(Path(settings.models_dir), spec.model_name)
        except OSError:
            size = 0
        lines.append(f"  {spec.key:<8} {spec.model_name:<16} " + (f"{size / 1e9:.2f} Go" if size else "absent"))
    return lines


def report(context: Context) -> str:
    s = context.settings
    out = [
        f"MyWhisper {__version__} — diagnostic du {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Système",
        f"Windows : {platform.platform()} ({platform.machine()})",
        f"Python : {platform.python_version()} · {'installé (exécutable)' if getattr(sys, 'frozen', False) else 'sources'}",
        f"Processeur : {platform.processor() or '?'} · {os.cpu_count()} cœurs logiques",
        "",
        "## Calcul",
        f"Utilisé : {context.device_description or '?'}",
        f"Modèle chargé : {context.model_loaded or 'aucun'}",
        f"Accélération installée : {context.runtime_variant or 'aucune'}",
    ]
    if context.cpu_notice:
        out.append(f"Repli processeur : {context.cpu_notice}")
    out += _gpu_lines()
    if context.adapters is not None:
        try:
            adapters = context.adapters()
        except Exception as exc:
            adapters = []
            out.append(f"Cartes graphiques : détection impossible ({exc})")
        for adapter in adapters:
            out.append(f"Carte graphique : {adapter.name} ({adapter.vendor}, pilote {adapter.driver or '?'})")
    out += ["", "## Bibliothèques"]
    out += [f"{name} : {version}" for name, version in package_versions().items()]
    out += ["", "## Modèles", *_models_lines(s)]
    out += ["", "## Audio", f"Micros détectés : {len(context.microphones)}"]
    out.append(f"Micro choisi : {'défaut de Windows' if s.input_device is None else 'personnalisé'}")
    if context.history_count is not None:
        out.append(f"Historique : {context.history_count} transcription(s)")
    out += ["", "## Réglages (sans le vocabulaire ni le contexte)"]
    for name, value in vars(s).items():
        if name not in PRIVATE_SETTINGS:
            out.append(f"{name} = {value!r}")
    out += ["", "## Derniers avertissements et erreurs"]
    issues = recent_issues(context.log_file) if context.log_file else []
    out += issues or ["(aucun)"]
    return "\n".join(out) + "\n"
