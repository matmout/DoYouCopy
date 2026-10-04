"""Build assets: the application icon (.ico) and the Windows version resource."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper import __version__  # noqa: E402
from mywhisper.ui import theme  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    """Microphone on a dark rounded square, in the app's accent colour."""
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.DARK.bg))
    radius = size * 0.22
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    icon = theme.icon("ph.microphone-fill", theme.DARK, "accent")
    margin = round(size * 0.16)
    icon.paint(p, margin, margin, size - 2 * margin, size - 2 * margin)
    p.end()
    return image


def write_ico(path: Path) -> None:
    """Multi-resolution .ico with PNG entries (supported since Windows Vista)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    pngs = []
    for size in SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        render(size).save(buffer, "PNG")
        pngs.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in pngs:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    path.write_bytes(header + entries + blobs)


def write_version_info(path: Path) -> None:
    parts = [int(x) for x in __version__.split(".")] + [0] * 4
    numbers = ", ".join(str(n) for n in parts[:4])
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040C04B0', [
      StringStruct('CompanyName', 'MyWhisper'),
      StringStruct('FileDescription', 'MyWhisper - transcription vocale locale'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'MyWhisper'),
      StringStruct('OriginalFilename', 'MyWhisper.exe'),
      StringStruct('ProductName', 'MyWhisper'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x040C, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    app = QApplication([])
    BUILD.mkdir(exist_ok=True)
    write_ico(BUILD / "mywhisper.ico")
    write_version_info(BUILD / "version_info.txt")
    print(__version__)
