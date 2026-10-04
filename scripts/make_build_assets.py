"""Build assets: the application icon (.ico) and the Windows version resource."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper import __version__  # noqa: E402
from mywhisper.ui.app_icon import write_ico  # noqa: E402


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
