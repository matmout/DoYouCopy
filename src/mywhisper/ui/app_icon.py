"""The application icon: a microphone in the accent colour on a dark rounded square.

One drawing for every place the icon appears: the window and taskbar (qicon), the
.ico embedded in MyWhisper.exe at build time (scripts/make_build_assets.py) and,
from a source checkout, the .ico of the shortcuts (no .exe to take it from).
Needs a QGuiApplication: the microphone comes from the Phosphor icon font.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from mywhisper.ui import theme

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
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


def qicon() -> QIcon:
    """Every size drawn on purpose: small sizes stay sharp in the taskbar."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(QPixmap.fromImage(render(size)))
    return icon


def ico_bytes() -> bytes:
    """Multi-resolution .ico with PNG entries (supported since Windows Vista)."""
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
        dim = 0 if size >= 256 else size  # 0 means 256 in an .ico directory entry
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def write_ico(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ico_bytes())
    return path
