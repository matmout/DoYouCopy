"""Downloads the GPU runtime that matches the graphics card: run by the installer
(MyWhisper.exe --setup-runtime) and from the "slower on this machine" banner."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from mywhisper.runtime import install, startup, store
from mywhisper.runtime.gpu_detect import Detection
from mywhisper.runtime.packages import RuntimePackage, package_for

log = logging.getLogger(__name__)


def gigabytes(size: int) -> str:
    return f"{size / 1024**3:.1f}".replace(".", ",") + " Go"


class _InstallJob(QObject):
    progress = Signal(str, int, int)
    finished = Signal(bool, str)  # GPU usable, message

    def __init__(self, package: RuntimePackage, cancel: threading.Event, probe=startup.probe_subprocess) -> None:
        super().__init__()
        self.package = package
        self.cancel = cancel
        self._probe = probe

    @Slot()
    def run(self) -> None:
        try:
            install.install(self.package, progress=self.progress.emit, cancel=self.cancel)
        except install.DownloadCancelled:
            self.finished.emit(False, "Téléchargement annulé. MyWhisper utilisera le processeur.")
            return
        except install.DownloadError as exc:
            self.finished.emit(False, f"{exc}\nMyWhisper utilisera le processeur.")
            return
        except Exception as exc:
            log.exception("Runtime install failed")
            self.finished.emit(False, f"Installation impossible : {exc}\nMyWhisper utilisera le processeur.")
            return
        self.progress.emit("probe", 0, 0)
        result = self._probe()
        if result.get("ok"):
            self.finished.emit(True, "Accélération graphique activée.")
            return
        log.warning("GPU probe after install failed: %s", result)
        store.remove(self.package)
        driver = "NVIDIA" if self.package.variant == "nvidia" else "AMD Adrenalin"
        self.finished.emit(
            False,
            "La carte graphique n'a pas pu être initialisée.\n"
            f"Mettez à jour le pilote {driver}, puis relancez cette installation depuis MyWhisper.\n"
            "En attendant, MyWhisper utilisera le processeur.",
        )


class RuntimeSetupDialog(QDialog):
    def __init__(self, detection: Detection, parent: QWidget | None = None, auto_start: bool = True, probe=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MyWhisper · Accélération graphique")
        self.setMinimumWidth(520)
        self.detection = detection
        self.package = package_for(detection.variant) if detection.has_gpu else None
        self.gpu_ready = False
        self._cancel = threading.Event()
        self._thread: QThread | None = None
        self._probe = probe

        self.title = QLabel()
        self.title.setObjectName("DialogTitle")
        self.title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status = QLabel()
        self.status.setProperty("mono", True)
        self.start_button = QPushButton("Télécharger")
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Utiliser le processeur")
        self.cancel_button.setObjectName("OutlineButton")
        self.cancel_button.clicked.connect(self._cancel_or_close)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.start_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addSpacing(4)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addStretch()
        layout.addLayout(buttons)

        if self.package is None:
            self.title.setText(startup.SLOW_TITLE)
            self.detail.setText(
                f"{detection.reason}.\n\nMyWhisper fonctionnera sur le processeur : la transcription "
                "reste possible, mais plus lente (le modèle Turbo est recommandé)."
            )
            self.start_button.hide()
            self.cancel_button.setText("Terminer")
        elif store.is_installed(self.package):
            self.title.setText("Accélération graphique déjà installée")
            self.detail.setText(f"{detection.reason}.")
            self.gpu_ready = True
            self.start_button.hide()
            self.cancel_button.setText("Terminer")
        else:
            self.title.setText(self.package.label)
            self.detail.setText(
                f"{detection.reason}.\n\nMyWhisper télécharge les composants qui lui permettent de transcrire "
                f"avec cette carte ({gigabytes(self.package.download_size)}), depuis leurs sources officielles."
            )
            if auto_start:
                self.start()

    # ---- install ---------------------------------------------------------

    def start(self) -> None:
        if self.package is None or self._thread is not None:
            return
        self.start_button.hide()
        self.cancel_button.setText("Annuler")
        self.progress.show()
        self.status.setText("Connexion…")
        job = _InstallJob(self.package, self._cancel, **({"probe": self._probe} if self._probe else {}))
        self._thread = QThread(self)
        job.moveToThread(self._thread)
        self._thread.started.connect(job.run)
        job.progress.connect(self._on_progress)
        job.finished.connect(self._on_finished)
        job.finished.connect(self._thread.quit)
        self._job = job  # keep a reference
        self._thread.start()

    def _on_progress(self, stage: str, done: int, total: int) -> None:
        if stage == "download":
            self.progress.setValue(int(done / max(total, 1) * 1000))
            self.status.setText(f"Téléchargement · {gigabytes(done)} / {gigabytes(total)}")
        elif stage == "extract":
            self.progress.setValue(int(done / max(total, 1) * 1000))
            self.status.setText(f"Installation · {done * 100 // max(total, 1)} %")
        else:
            self.progress.setRange(0, 0)  # indeterminate while the card is tested
            self.status.setText("Vérification de la carte graphique…")

    def _on_finished(self, ok: bool, message: str) -> None:
        self.gpu_ready = ok
        self._thread = None
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000 if ok else 0)
        self.progress.setVisible(ok)
        self.title.setText("Accélération graphique activée" if ok else startup.SLOW_TITLE)
        self.status.setText("")
        self.detail.setText(message)
        self.cancel_button.setText("Terminer")

    def _cancel_or_close(self) -> None:
        if self._thread is not None:
            self._cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("Annulation…")
            return
        self.accept() if self.gpu_ready else self.reject()

    def closeEvent(self, event) -> None:
        if self._thread is not None:
            self._cancel.set()
            self._thread.quit()
            self._thread.wait(10000)
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel_or_close()
            return
        super().keyPressEvent(event)
