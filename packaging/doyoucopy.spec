# PyInstaller spec: a folder build (faster start, fewer antivirus false positives
# than a single exe), no console, no UPX.
#
# CTranslate2 is excluded from the frozen archive on purpose: the CPU/CUDA build
# from PyPI is shipped as a plain folder (ct2_cpu) so that a downloaded GPU runtime
# can take precedence on sys.path (see doyoucopy/runtime/store.py).
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BUILD = os.path.join(ROOT, "build")

datas = [
    *collect_data_files("doyoucopy.ui", includes=["resources/fonts/*"]),
    *collect_data_files("qtawesome"),
    *collect_data_files("faster_whisper"),  # Silero VAD model
    (os.path.join(BUILD, "ct2_cpu"), "ct2_cpu"),
]

hiddenimports = [
    *collect_submodules("doyoucopy"),
    # what ctranslate2 imports, since the analysis does not see it
    "numpy", "yaml", "asyncio", "queue", "struct", "glob", "shutil", "importlib.resources", "enum", "ctypes",
]

excludes = [
    "ctranslate2", "rocm_sdk", "rocm_sdk_core", "rocm_sdk_libraries_custom",
    "_rocm_sdk_core", "_rocm_sdk_libraries_custom",
    "torch", "tensorflow", "tkinter", "matplotlib", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtCharts", "PySide6.QtDataVisualization",
]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
# The dependency scan of ct2_cpu copies its DLLs next to the exe as well. Drop those
# copies: a GPU runtime must load its own ctranslate2.dll, never a stray one.
CT2_DLLS = {"ctranslate2.dll", "libiomp5md.dll", "cudnn64_9.dll"}
a.binaries = [b for b in a.binaries if not (os.path.basename(b[0]).lower() in CT2_DLLS and os.sep not in b[0] and "/" not in b[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DoYouCopy",
    console=False,
    icon=os.path.join(BUILD, "doyoucopy.ico"),
    version=os.path.join(BUILD, "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="DoYouCopy")
