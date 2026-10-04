"""Microsoft Store package (MSIX): detection, redirected folders, autostart, shortcuts."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from doyoucopy.desktop import packaging, shortcuts
from doyoucopy.dictation import autostart

FAMILY = "TrachselLabs.DoYouCopy_7zb5jdp1hfh86"


@pytest.fixture
def packaged(monkeypatch):
    monkeypatch.setattr(packaging, "family_name", lambda: FAMILY)


def test_tests_do_not_run_from_a_package():
    packaging.family_name.cache_clear()
    assert not packaging.is_packaged()


def test_real_path_unchanged_outside_a_package(tmp_path):
    assert packaging.real_path(tmp_path / "logs") == tmp_path / "logs"


def test_real_path_follows_the_package_redirection(packaged, tmp_path, monkeypatch):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    cache = local / "Packages" / FAMILY / "LocalCache"

    logs = local / "DoYouCopy" / "logs"
    assert packaging.real_path(logs) == logs  # nothing redirected yet
    (cache / "Local" / "DoYouCopy" / "logs").mkdir(parents=True)
    assert packaging.real_path(logs) == cache / "Local" / "DoYouCopy" / "logs"

    (cache / "Roaming" / "DoYouCopy").mkdir(parents=True)
    assert packaging.real_path(roaming / "DoYouCopy") == cache / "Roaming" / "DoYouCopy"
    assert packaging.real_path(tmp_path / "elsewhere") == tmp_path / "elsewhere"


def test_no_shortcuts_from_the_package(packaged):
    assert not shortcuts.available()
    assert not shortcuts.set_enabled(shortcuts.DESKTOP, True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows autostart")
def test_autostart_uses_the_startup_task_from_the_package(packaged, monkeypatch):
    import winreg

    def no_registry(*args, **kwargs):
        raise AssertionError("the Run key is virtualized in a package")

    monkeypatch.setattr(winreg, "OpenKey", no_registry)
    calls = []
    monkeypatch.setattr(autostart, "_task_enabled", lambda: True)
    monkeypatch.setattr(autostart, "_set_task", lambda enabled: calls.append(enabled) or True)
    assert autostart.is_enabled()
    assert autostart.set_enabled(False) and calls == [False]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows autostart")
def test_startup_task_failure_is_reported(packaged):
    # Not really packaged: the WinRT call fails, which must read as "not done".
    assert autostart._set_task(True) is False
    assert autostart._task_enabled() is False


def test_settings_hide_shortcuts_from_the_package(packaged):
    from doyoucopy.config import Settings
    from doyoucopy.ui import settings_dialog

    QApplication.instance() or QApplication([])
    dialog = settings_dialog.SettingsDialog(Settings())
    assert dialog.shortcut_checks == {}
    dialog.close()
