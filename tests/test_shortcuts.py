"""Desktop and Start menu shortcuts (real .lnk files, in a temporary folder)."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from mywhisper.desktop import shortcuts
from mywhisper.desktop.shortcuts import Target

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folders(tmp_path, monkeypatch):
    places = {
        shortcuts.DESKTOP: tmp_path / "Bureau" / "MyWhisper.lnk",
        shortcuts.START_MENU: tmp_path / "Programs" / "MyWhisper" / "MyWhisper.lnk",
    }
    monkeypatch.setattr(shortcuts, "location", places.__getitem__)
    monkeypatch.setattr(shortcuts, "_checkout_icon", lambda: None)  # nothing written to the real profile
    return places


def test_command_line():
    assert Target(Path("C:/A b/MyWhisper.exe")).command_line("--minimized") == '"C:\\A b\\MyWhisper.exe" --minimized'
    assert Target(Path("py.exe"), "-m mywhisper").command_line() == '"py.exe" -m mywhisper'


@windows_only
def test_shortcut_launches_the_app_with_its_identity(app, tmp_path):
    path = tmp_path / "MyWhisper.lnk"
    shortcuts.create(path, Target(Path(sys.executable), "-m mywhisper"))
    info = shortcuts.read(path)
    assert Path(info.program) == Path(sys.executable) and info.arguments == "-m mywhisper"
    assert info.app_id == shortcuts.APP_ID == "MyWhisper.MyWhisper"


@windows_only
def test_enable_and_disable_both_kinds(app, folders):
    for kind, path in folders.items():
        assert not shortcuts.exists(kind)
        assert shortcuts.set_enabled(kind, True) and shortcuts.exists(kind) and path.is_file()
        assert shortcuts.set_enabled(kind, False) and not path.exists()
    assert not folders[shortcuts.START_MENU].parent.exists()  # the empty MyWhisper folder goes too


@windows_only
def test_start_menu_folder_kept_while_the_uninstaller_link_is_there(app, folders):
    path = folders[shortcuts.START_MENU]
    shortcuts.set_enabled(shortcuts.START_MENU, True)
    (path.parent / "Désinstaller MyWhisper.lnk").write_bytes(b"")
    shortcuts.set_enabled(shortcuts.START_MENU, False)
    assert not path.exists() and path.parent.is_dir()


def test_settings_checkbox_shows_what_really_happened(app, folders, monkeypatch):
    from mywhisper.config import Settings
    from mywhisper.ui import settings_dialog

    warnings = []
    monkeypatch.setattr(shortcuts, "available", lambda: True)
    monkeypatch.setattr(settings_dialog.QMessageBox, "warning", lambda *args: warnings.append(args))
    dialog = settings_dialog.SettingsDialog(Settings())
    check = dialog.shortcut_checks[shortcuts.DESKTOP]
    assert not check.isChecked() and check.isEnabled()

    monkeypatch.setattr(shortcuts, "set_enabled", lambda kind, enabled: False)  # e.g. Desktop not writable
    check.setChecked(True)
    assert not check.isChecked() and len(warnings) == 1

    created = []
    monkeypatch.setattr(shortcuts, "set_enabled", lambda kind, enabled: created.append((kind, enabled)) or True)
    dialog.shortcut_checks[shortcuts.START_MENU].setChecked(True)
    assert created == [(shortcuts.START_MENU, True)]
    dialog.close()
