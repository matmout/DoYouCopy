"""Picks the inference device: the GPU seen by CTranslate2 (NVIDIA CUDA or AMD ROCm), else CPU.

Import this module before PySide6 so the DLL directories registered by
ctranslate2 are in place before Qt loads its own libraries. In the packaged app,
doyoucopy.runtime.startup.prepare() must run first: it picks which ctranslate2 is imported.
"""

from __future__ import annotations

import logging

from doyoucopy.core.types import DeviceConfig

log = logging.getLogger(__name__)

CPU = DeviceConfig("cpu", "int8", "Processeur · int8")


# Offered in the settings, best first; filtered by what the hardware supports.
GPU_COMPUTE_TYPES = ("float16", "int8_float16", "bfloat16", "int8", "float32")
CPU_COMPUTE_TYPES = ("int8", "int8_float32", "float32")


def supported_compute_types(device: str) -> list[str]:
    """What CTranslate2 can run on "cuda" or "cpu", in the order of the settings menu."""
    try:
        import ctranslate2

        if device == "cuda" and ctranslate2.get_cuda_device_count() == 0:
            return []
        supported = ctranslate2.get_supported_compute_types(device)
    except Exception:
        log.exception("Could not query the compute types of %s", device)
        return [] if device == "cuda" else ["int8", "float32"]
    order = GPU_COMPUTE_TYPES if device == "cuda" else CPU_COMPUTE_TYPES
    return [t for t in order if t in supported]


def gpu_device(compute_type: str = "auto") -> DeviceConfig | None:
    supported = supported_compute_types("cuda")
    if not supported:
        return None
    if compute_type not in supported:
        compute_type = "float16" if "float16" in supported else "float32"
    return DeviceConfig("cuda", compute_type, f"GPU · {compute_type}")


def cpu_device(compute_type: str = "auto") -> DeviceConfig:
    if compute_type == CPU.compute_type or compute_type not in CPU_COMPUTE_TYPES:
        return CPU
    return DeviceConfig("cpu", compute_type, f"Processeur · {compute_type}")


def detect_device(preference: str = "auto", compute_type: str = "auto") -> DeviceConfig:
    """preference: "auto" (GPU if available), "gpu" or "cpu". compute_type: "auto" or a
    CTranslate2 type; a type the device cannot run falls back to its default."""
    if preference == "cpu":
        return cpu_device(compute_type)
    gpu = gpu_device(compute_type)
    if gpu is None:
        log.warning("No GPU found, falling back to CPU")
        return cpu_device(compute_type)
    return gpu
