"""Picks the inference device: AMD GPU through the ROCm build of CTranslate2, else CPU.

Import this module before PySide6 so the ROCm DLL directories registered by
ctranslate2 are in place before Qt loads its own libraries.
"""

from __future__ import annotations

import logging

from mywhisper.core.types import DeviceConfig

log = logging.getLogger(__name__)

CPU = DeviceConfig("cpu", "int8", "CPU · int8")


def gpu_device() -> DeviceConfig | None:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() == 0:
            return None
        supported = ctranslate2.get_supported_compute_types("cuda")
    except Exception:
        log.exception("ROCm/HIP initialisation failed")
        return None
    compute_type = "float16" if "float16" in supported else "float32"
    return DeviceConfig("cuda", compute_type, f"GPU ROCm · {compute_type}")


def detect_device(preference: str = "auto") -> DeviceConfig:
    """preference: "auto" (GPU if available), "gpu" or "cpu"."""
    if preference == "cpu":
        return CPU
    gpu = gpu_device()
    if gpu is None:
        log.warning("No ROCm GPU found, falling back to CPU")
        return CPU
    return gpu
