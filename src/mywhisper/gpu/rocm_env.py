"""Picks the inference device: the GPU seen by CTranslate2 (NVIDIA CUDA or AMD ROCm), else CPU.

Import this module before PySide6 so the DLL directories registered by
ctranslate2 are in place before Qt loads its own libraries. In the packaged app,
mywhisper.runtime.startup.prepare() must run first: it picks which ctranslate2 is imported.
"""

from __future__ import annotations

import logging

from mywhisper.core.types import DeviceConfig

log = logging.getLogger(__name__)

CPU = DeviceConfig("cpu", "int8", "Processeur · int8")


def gpu_device() -> DeviceConfig | None:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() == 0:
            return None
        supported = ctranslate2.get_supported_compute_types("cuda")
    except Exception:
        log.exception("GPU initialisation failed")
        return None
    compute_type = "float16" if "float16" in supported else "float32"
    return DeviceConfig("cuda", compute_type, f"GPU · {compute_type}")


def detect_device(preference: str = "auto") -> DeviceConfig:
    """preference: "auto" (GPU if available), "gpu" or "cpu"."""
    if preference == "cpu":
        return CPU
    gpu = gpu_device()
    if gpu is None:
        log.warning("No GPU found, falling back to CPU")
        return CPU
    return gpu
