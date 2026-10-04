import logging
import sys
import threading

from doyoucopy import diagnostics
from doyoucopy.config import Settings
from doyoucopy.runtime.gpu_detect import Adapter


def test_recent_issues_keeps_warnings_and_tracebacks(tmp_path):
    log_file = tmp_path / "doyoucopy.log"
    log_file.write_text(
        "2026-10-04 10:00:00,000 INFO a: démarrage\n"
        "2026-10-04 10:00:01,000 ERROR b: Model load failed\n"
        "Traceback (most recent call last):\n"
        "  RuntimeError: hipErrorNoDevice\n"
        "2026-10-04 10:00:02,000 INFO a: suite\n"
        "2026-10-04 10:00:03,000 WARNING c: micro absent\n",
        encoding="utf-8",
    )
    assert diagnostics.recent_issues(log_file) == [
        "2026-10-04 10:00:01,000 ERROR b: Model load failed",
        "Traceback (most recent call last):",
        "  RuntimeError: hipErrorNoDevice",
        "2026-10-04 10:00:03,000 WARNING c: micro absent",
    ]
    assert diagnostics.recent_issues(log_file, limit=1) == ["2026-10-04 10:00:03,000 WARNING c: micro absent"]
    assert diagnostics.recent_issues(tmp_path / "absent.log") == []


def test_report_describes_the_machine_but_not_the_content(tmp_path):
    settings = Settings(
        hotwords=["Projet Secret"], replacements=[["x", "Dupuis"]], initial_prompt="Réunion confidentielle",
        input_device="Micro de Claire",
    )
    log_file = tmp_path / "doyoucopy.log"
    log_file.write_text("2026-10-04 10:00:01,000 ERROR b: boom\n", encoding="utf-8")
    text = diagnostics.report(
        diagnostics.Context(
            settings=settings,
            device_description="GPU · float16",
            runtime_variant="amd",
            model_loaded="large-v3-turbo",
            microphones=["Micro de Claire"],
            history_count=3,
            log_file=log_file,
            adapters=lambda: [Adapter("AMD Radeon RX 7800 XT", "amd", "32.0.1")],
        )
    )
    for expected in ("GPU · float16", "large-v3-turbo", "RX 7800 XT", "Python", "faster-whisper",
                     "model_key = 'turbo'", "Historique : 3", "ERROR b: boom"):
        assert expected in text
    for secret in ("Projet Secret", "Dupuis", "confidentielle", "Claire"):
        assert secret not in text


def test_report_survives_a_failing_detection():
    def broken():
        raise OSError("powershell absent")

    text = diagnostics.report(diagnostics.Context(settings=Settings(), adapters=broken))
    assert "détection impossible" in text and "(aucun)" in text


def test_setup_logging_writes_a_file_and_catches_uncaught_errors(tmp_path, monkeypatch):
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    try:
        path = diagnostics.setup_logging(tmp_path / "logs", console=False)
        logging.getLogger("doyoucopy.test").warning("attention")
        try:
            raise ValueError("inattendue")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        for handler in root.handlers:
            handler.flush()
        content = path.read_text(encoding="utf-8")
        assert "WARNING doyoucopy.test: attention" in content
        assert "CRITICAL doyoucopy: Uncaught exception" in content and "ValueError: inattendue" in content
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = handlers
        root.setLevel(level)
