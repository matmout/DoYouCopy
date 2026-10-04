import json

import pytest

from doyoucopy import legacy


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setattr(legacy, "_move_autostart", lambda: None)  # never touch the real registry
    return local, roaming


def test_data_of_mywhisper_moves_to_doyoucopy(appdata):
    local, roaming = appdata
    old_local = local / "MyWhisper"
    (old_local / "models" / "large-v3").mkdir(parents=True)
    (old_local / "models" / "large-v3" / "model.bin").write_bytes(b"x")
    (old_local / "history").mkdir()
    (old_local / "history" / "history.db").write_bytes(b"db")
    (roaming / "MyWhisper").mkdir(parents=True)
    settings = {"models_dir": str(old_local / "models"), "theme": "dark"}
    (roaming / "MyWhisper" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    moved = legacy.migrate()

    new_local = local / "DoYouCopy"
    assert (new_local / "models" / "large-v3" / "model.bin").read_bytes() == b"x"
    assert (new_local / "history" / "history.db").exists()
    assert not old_local.exists() and not (roaming / "MyWhisper").exists()
    saved = json.loads((roaming / "DoYouCopy" / "settings.json").read_text(encoding="utf-8"))
    assert saved == {"models_dir": str(new_local / "models"), "theme": "dark"}
    assert len(moved) == 3
    assert legacy.migrate() == []  # nothing left to do


def test_items_already_in_the_new_folder_are_kept(appdata):
    local, _ = appdata
    (local / "MyWhisper" / "logs").mkdir(parents=True)
    (local / "MyWhisper" / "logs" / "old.log").write_text("old", encoding="utf-8")
    (local / "DoYouCopy" / "logs").mkdir(parents=True)

    assert legacy.migrate() == []
    assert not (local / "DoYouCopy" / "logs" / "old.log").exists()
    assert (local / "MyWhisper" / "logs" / "old.log").exists()  # left in place, never overwritten


def test_a_custom_models_folder_is_left_alone(appdata, tmp_path):
    _, roaming = appdata
    (roaming / "DoYouCopy").mkdir(parents=True)
    custom = {"models_dir": str(tmp_path / "D" / "Models")}
    (roaming / "DoYouCopy" / "settings.json").write_text(json.dumps(custom), encoding="utf-8")
    legacy.migrate()
    assert json.loads((roaming / "DoYouCopy" / "settings.json").read_text(encoding="utf-8")) == custom
