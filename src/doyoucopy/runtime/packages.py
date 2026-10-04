"""Pinned downloads of each GPU runtime: exact versions and SHA-256, nothing floating.

- NVIDIA: the CTranslate2 build shipped with the app (PyPI, CUDA 12) only lacks
  cuBLAS and the cuDNN 9 sub-libraries. cuDNN must match the cudnn64_9.dll stub
  bundled in that wheel (9.10.2), cuBLAS the CUDA 12.8 toolkit it was built with.
- AMD: the ROCm build of CTranslate2 (one wheel inside a GitHub release zip) and the
  ROCm 7.2 runtime it is linked against, laid out side by side as its __init__ expects.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

CT2_VERSION = "4.8.2"


@dataclass(frozen=True)
class Download:
    url: str
    sha256: str
    size: int
    member: str | None = None  # wheel to take out of a zip archive

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class RuntimePackage:
    variant: str  # "nvidia" or "amd"
    label: str
    version: str  # bump to force a reinstall
    downloads: tuple[Download, ...]
    disk_needed: int  # bytes: downloads + extracted files

    @property
    def download_size(self) -> int:
        return sum(d.size for d in self.downloads)


def python_tag() -> str:
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


_ROCM = "https://repo.radeon.com/rocm/windows/rocm-rel-7.2"
_PYPI = "https://files.pythonhosted.org/packages"
_GB = 1024**3

_PACKAGES: dict[tuple[str, str], RuntimePackage] = {
    ("nvidia", "cp313"): RuntimePackage(
        variant="nvidia",
        label="Accélération NVIDIA (CUDA 12)",
        version="cuda12.8-cudnn9.10-1",
        downloads=(
            Download(
                f"{_PYPI}/74/65/d9db5b0754559f6ed279c4a6cf1192dbf581f7d01e5d3d2882f577936049/"
                "nvidia_cublas_cu12-12.8.5.5-py3-none-win_amd64.whl",
                "1e272895b82946b4db6f592d9080291fb60f78c9fe253a5c71ba5ebb74864c3e",
                567543364,
            ),
            Download(
                f"{_PYPI}/3d/90/0bd6e586701b3a890fd38aa71c387dab4883d619d6e5ad912ccbd05bfd67/"
                "nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl",
                "c6288de7d63e6cf62988f0923f96dc339cea362decb1bf5b3141883392a7d65e",
                692992268,
            ),
        ),
        disk_needed=4 * _GB,
    ),
    ("amd", "cp313"): RuntimePackage(
        variant="amd",
        label="Accélération AMD (ROCm 7.2)",
        version=f"rocm7.2-ct2{CT2_VERSION}-1",
        downloads=(
            Download(
                f"https://github.com/OpenNMT/CTranslate2/releases/download/v{CT2_VERSION}/"
                "rocm-python-wheels-Windows.zip",
                "43da4baa5feaee49f77e176277a9647f99c493173c81a0bc60f491cac97532c2",
                137538158,
                member=f"temp-windows/ctranslate2-{CT2_VERSION}-cp313-cp313-win_amd64.whl",
            ),
            Download(
                f"{_ROCM}/rocm_sdk_core-7.2.0.dev0-py3-none-win_amd64.whl",
                "f8dac46ea54d570dd73a694e9f6793e80889a8168dd484be57b0d2f65079dde3",
                636833391,
            ),
            Download(
                f"{_ROCM}/rocm_sdk_libraries_custom-7.2.0.dev0-py3-none-win_amd64.whl",
                "29a155b8f0da7b4ea05481ba665dc08749462a66bfc7cee27a6976bdea41f0cc",
                492439790,
            ),
        ),
        disk_needed=6 * _GB,
    ),
}


def package_for(variant: str, tag: str | None = None) -> RuntimePackage | None:
    """None for the CPU, or when no pinned build exists for this Python version."""
    return _PACKAGES.get((variant, tag or python_tag()))
