"""Startup choice of the runtime, the GPU probe, and the CPU fallback explanation."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from mywhisper.runtime import gpu_detect, store
from mywhisper.runtime.packages import package_for

log = logging.getLogger(__name__)

SLOW_TITLE = "Transcription plus lente sur cette machine"


@dataclass(frozen=True)
class RuntimeChoice:
    variant: str | None  # runtime put on the path: "nvidia", "amd", "dev" (source checkout) or None
    forced_cpu: bool = False  # "device": "cpu" in the settings


@dataclass(frozen=True)
class CpuNotice:
    """Shown when transcription runs on the CPU: why, and what can be done."""

    title: str
    detail: str
    install_variant: str | None = None  # a supported card without its runtime: offer the download


def prepare(device_preference: str) -> RuntimeChoice:
    """Puts the right ctranslate2 on the path. Call before importing ctranslate2."""
    forced_cpu = device_preference == "cpu"
    # An installed runtime is always activated, even when the CPU is chosen: the user
    # can then switch to the GPU in the settings without restarting.
    for variant in (gpu_detect.NVIDIA, gpu_detect.AMD):
        package = package_for(variant)
        if package is not None and store.is_installed(package):
            store.activate(package)
            log.info("GPU runtime: %s", package.label)
            return RuntimeChoice(variant, forced_cpu)
    store.activate(None)
    return RuntimeChoice(None if store.is_frozen() else "dev", forced_cpu)


def cpu_notice(choice: RuntimeChoice, detection: gpu_detect.Detection | None = None) -> CpuNotice | None:
    """Why the CPU is used. detection is computed lazily (a PowerShell call)."""
    if choice.forced_cpu:
        return None  # the user's own choice
    if choice.variant in (gpu_detect.NVIDIA, gpu_detect.AMD):
        driver = "NVIDIA" if choice.variant == gpu_detect.NVIDIA else "AMD Adrenalin"
        return CpuNotice(
            SLOW_TITLE,
            f"La carte graphique n'a pas pu être initialisée. Mettez à jour le pilote {driver}, puis relancez MyWhisper.",
        )
    detection = detection or gpu_detect.detect()
    package = package_for(detection.variant) if detection.has_gpu else None
    if package is not None:
        return CpuNotice(
            SLOW_TITLE,
            f"{detection.reason}. Son accélération n'est pas encore installée "
            f"({package.download_size / 1024**3:.1f} Go à télécharger).",
            install_variant=detection.variant,
        )
    return CpuNotice(SLOW_TITLE, f"{detection.reason}. MyWhisper utilise le processeur.")


# ---- probe ----------------------------------------------------------------


def probe() -> dict:
    """In the current process: what ctranslate2 sees."""
    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
        types = sorted(ctranslate2.get_supported_compute_types("cuda")) if count else []
        return {"ok": count > 0, "devices": count, "compute_types": types, "ct2": ctranslate2.__version__}
    except Exception as exc:  # DLL load failures surface as OSError / ImportError
        log.exception("GPU probe failed")
        return {"ok": False, "error": str(exc)}


def probe_subprocess(timeout_s: float = 120) -> dict:
    """A fresh process, so a runtime just installed is loaded the way the app will load it."""
    out = store.runtime_root() / "probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    command = [sys.executable] if store.is_frozen() else [sys.executable, "-m", "mywhisper"]
    try:
        subprocess.run(
            [*command, "--probe", str(out)],
            timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        return json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc)}


def write_probe(path: Path) -> None:
    path.write_text(json.dumps(probe()), encoding="utf-8")
