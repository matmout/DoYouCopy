"""Build assets: the application icon (.ico), the Windows version resource and, for the
Microsoft Store package, the MSIX manifest and its logos (build/msix)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from doyoucopy import __version__  # noqa: E402
from doyoucopy.ui.app_icon import render, write_ico  # noqa: E402


def write_version_info(path: Path) -> None:
    parts = [int(x) for x in __version__.split(".")] + [0] * 4
    numbers = ", ".join(str(n) for n in parts[:4])
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', 'DoYouCopy'),
      StringStruct('FileDescription', 'DoYouCopy - transcription vocale locale'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'DoYouCopy'),
      StringStruct('OriginalFilename', 'DoYouCopy.exe'),
      StringStruct('ProductName', 'DoYouCopy'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def msix_version() -> str:
    """1.1.0 -> 1.1.0.0: four numbers, the last one 0 (reserved by the Store)."""
    parts = ([int(x) for x in __version__.split(".")] + [0, 0])[:3]
    return ".".join(str(n) for n in parts) + ".0"


# Logos of the package: (file name, width, height, icon size relative to the height)
MSIX_LOGOS = (
    ("Square44x44Logo", 44, 44, 1.0),
    ("Square150x150Logo", 150, 150, 0.66),
    ("Wide310x150Logo", 310, 150, 0.66),
    ("StoreLogo", 50, 50, 1.0),
)
TARGET_SIZES = (16, 24, 32, 48, 256)  # taskbar, Start menu, Explorer


def _logo(width: int, height: int, ratio: float) -> QImage:
    """The icon centred on a transparent canvas."""
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    size = round(height * ratio)
    painter = QPainter(image)
    painter.drawImage(QRect((width - size) // 2, (height - size) // 2, size, size), render(size))
    painter.end()
    return image


def write_msix(folder: Path) -> None:
    """build/msix: AppxManifest.xml (identity from packaging/msix/identity.json) and
    Assets/*.png, with the scale and target-size variants makepri indexes."""
    assets = folder / "Assets"
    assets.mkdir(parents=True, exist_ok=True)
    for old in assets.glob("*.png"):
        old.unlink()
    for name, width, height, ratio in MSIX_LOGOS:
        for scale in (100, 200):
            factor = scale / 100
            _logo(round(width * factor), round(height * factor), ratio).save(str(assets / f"{name}.scale-{scale}.png"))
    for size in TARGET_SIZES:
        for suffix in ("", "_altform-unplated"):
            render(size).save(str(assets / f"Square44x44Logo.targetsize-{size}{suffix}.png"))

    identity = json.loads((ROOT / "packaging" / "msix" / "identity.json").read_text(encoding="utf-8"))
    manifest = (ROOT / "packaging" / "msix" / "AppxManifest.template.xml").read_text(encoding="utf-8")
    values = {**identity, "Version": msix_version()}
    for key, value in values.items():
        manifest = manifest.replace("{" + key + "}", value)
    (folder / "AppxManifest.xml").write_text(manifest, encoding="utf-8")


if __name__ == "__main__":
    app = QApplication([])
    BUILD.mkdir(exist_ok=True)
    write_ico(BUILD / "doyoucopy.ico")
    write_version_info(BUILD / "version_info.txt")
    write_msix(BUILD / "msix")
    print(__version__)
