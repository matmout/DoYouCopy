from pathlib import Path

from mywhisper.config import Settings


def test_roundtrip(tmp_path: Path):
    path = tmp_path / "sub" / "settings.json"
    Settings(model_key="precise", language="fr", vad_filter=False, input_device="Micro USB").save(path)
    loaded = Settings.load(path)
    assert (loaded.model_key, loaded.language, loaded.vad_filter, loaded.input_device) == (
        "precise", "fr", False, "Micro USB",
    )


def test_missing_file_gives_defaults(tmp_path: Path):
    assert Settings.load(tmp_path / "absent.json") == Settings()


def test_corrupt_file_gives_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_unknown_keys_ignored(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"model_key": "precise", "obsolete": 1}', encoding="utf-8")
    assert Settings.load(path).model_key == "precise"


def test_models_dir_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MYWHISPER_MODELS_DIR", str(tmp_path))
    assert Settings().models_dir == str(tmp_path)
