"""The application icon: a walkie-talkie sending radio waves, for "Do you copy?".

One drawing for every place the icon appears: the window and taskbar (qicon), the
.ico embedded in DoYouCopy.exe at build time (scripts/make_build_assets.py) and,
from a source checkout, the .ico of the shortcuts (no .exe to take it from).
Drawn with QPainter, so every size is sharp.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap

from doyoucopy.ui import theme

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QImage:
    """A walkie-talkie sending radio waves ("Do you copy?"), in the accent colour on a
    dark rounded square. Vector drawing on a 0-1 grid; small sizes drop the details."""
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size, size)
    bg, accent = QColor(theme.DARK.bg), QColor(theme.DARK.accent)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(0, 0, 1, 1), 0.22, 0.22)

    p.setBrush(accent)
    p.drawRoundedRect(QRectF(0.25, 0.13, 0.07, 0.24), 0.035, 0.035)  # antenna
    p.drawRoundedRect(QRectF(0.20, 0.31, 0.38, 0.56), 0.08, 0.08)  # body
    if size >= 32:  # speaker grille and push-to-talk screen, in the background colour
        p.setBrush(bg)
        for y in (0.42, 0.50, 0.58):
            p.drawRoundedRect(QRectF(0.28, y, 0.22, 0.04), 0.02, 0.02)
        p.drawRoundedRect(QRectF(0.30, 0.68, 0.18, 0.10), 0.03, 0.03)

    pen = QPen(accent, 0.065 if size >= 32 else 0.09)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    radii = (0.14, 0.27) if size >= 24 else (0.20,)
    for r in radii:  # waves from the top right of the walkie-talkie
        p.drawArc(QRectF(0.56 - r, 0.30 - r, 2 * r, 2 * r), -60 * 16, 105 * 16)
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
