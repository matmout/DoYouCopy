"""Which graphics card is in this PC, and which GPU runtime it can use.

Windows lists the adapters through WMI (Win32_VideoController). The PCI vendor id
in PNPDeviceID is reliable; the model name decides whether an AMD card is one of
the architectures the ROCm build of CTranslate2 is compiled for. A real GPU probe
confirms the choice once the runtime is installed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass

from doyoucopy.i18n import tr

log = logging.getLogger(__name__)

NVIDIA, AMD, CPU = "nvidia", "amd", "cpu"
VENDOR_IDS = {"10DE": NVIDIA, "1002": AMD, "8086": "intel"}

# ROCm wheels of CTranslate2: gfx1030 (RX 6800/6900), gfx110x (RX 7000, Radeon 7x0M),
# gfx115x (Radeon 8x0M, 8050S/8060S), gfx120x (RX 9000).
_AMD_SUPPORTED = re.compile(
    r"RX\s*(6[89]\d0|7\d{3}|9\d{3})"
    r"|PRO\s*W(68\d0|7\d{3}|9\d{3})"
    r"|Radeon\s*(7[0-9]0M|8[0-9]0M|80[56]0S)",
    re.IGNORECASE,
)
# CUDA 12 needs Maxwell (compute capability 5.0) or newer.
_NVIDIA_TOO_OLD = re.compile(r"\bGTX?\s*[4-7]\d\d\b|\bGT\s*\d{3}\b|\bNVS\b", re.IGNORECASE)

_POWERSHELL = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name, PNPDeviceID, DriverVersion | ConvertTo-Json -Compress"
)


@dataclass(frozen=True)
class Adapter:
    name: str
    vendor: str  # "nvidia", "amd", "intel" or "other"
    driver: str = ""


@dataclass(frozen=True)
class Detection:
    variant: str  # "nvidia", "amd" or "cpu"
    adapter: Adapter | None
    reason: str  # for the user: why this choice

    @property
    def has_gpu(self) -> bool:
        return self.variant != CPU


def parse_adapters(raw: str) -> list[Adapter]:
    if not raw.strip():
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    adapters = []
    for item in data:
        name = (item.get("Name") or "").strip()
        match = re.search(r"VEN_([0-9A-F]{4})", item.get("PNPDeviceID") or "", re.IGNORECASE)
        vendor = VENDOR_IDS.get(match.group(1).upper(), "other") if match else "other"
        if name:
            adapters.append(Adapter(name, vendor, (item.get("DriverVersion") or "").strip()))
    return adapters


def _powershell() -> str:
    """Full path: a bare name is looked up in the current folder before System32."""
    system_root = os.environ.get("SYSTEMROOT") or r"C:\Windows"
    return os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def list_adapters() -> list[Adapter]:
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,  # the output is parsed whatever the exit code
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return parse_adapters(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        log.exception("Graphics adapter detection failed")
        return []


def classify(adapters: list[Adapter]) -> Detection:
    """NVIDIA first (dedicated card), then a supported AMD card, else the CPU."""
    nvidia = [a for a in adapters if a.vendor == NVIDIA]
    for adapter in nvidia:
        if not _NVIDIA_TOO_OLD.search(adapter.name):
            return Detection(NVIDIA, adapter, tr("Carte NVIDIA détectée : {name}").format(name=adapter.name))
    for adapter in adapters:
        if adapter.vendor == AMD and _AMD_SUPPORTED.search(adapter.name):
            return Detection(AMD, adapter, tr("Carte AMD détectée : {name}").format(name=adapter.name))
    if nvidia:
        return Detection(
            CPU, nvidia[0], tr("{name} : carte trop ancienne pour l'accélération (CUDA 12)").format(name=nvidia[0].name)
        )
    amd = next((a for a in adapters if a.vendor == AMD), None)
    if amd:
        return Detection(
            CPU,
            amd,
            tr("{name} : non prise en charge par l'accélération AMD (Radeon RX 6800 et plus récentes)").format(name=amd.name),
        )
    if adapters:
        return Detection(
            CPU, adapters[0], tr("{name} : pas d'accélération disponible pour cette carte").format(name=adapters[0].name)
        )
    return Detection(CPU, None, tr("Aucune carte graphique compatible détectée"))


def detect() -> Detection:
    return classify(list_adapters())
