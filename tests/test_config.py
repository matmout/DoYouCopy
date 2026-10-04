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


def test_vocabulary_and_dictation_roundtrip(tmp_path: Path):
    path = tmp_path / "settings.json"
    Settings(
        hotwords=["ROCm", "  ", "Mme Dupuis"],
        replacements=[["rock m", "ROCm"]],
        dictation_hotkey="Ctrl+Alt+D",
        dictation_mode="toggle",
    ).save(path)
    loaded = Settings.load(path)
    assert loaded.replacements == [["rock m", "ROCm"]]
    assert (loaded.dictation_hotkey, loaded.dictation_mode) == ("Ctrl+Alt+D", "toggle")
    assert loaded.hotwords_prompt() == "ROCm, Mme Dupuis"
    assert Settings().hotwords_prompt() is None


def test_invalid_values_fall_back_one_by_one(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"model_key": "precise", "beam_size": "5", "hotwords": null, "cpu_threads": true,'
        ' "vad_threshold": 1, "language": null, "input_device": 3}',
        encoding="utf-8",
    )
    loaded = Settings.load(path)
    assert loaded.model_key == "precise"
    assert (loaded.beam_size, loaded.hotwords, loaded.cpu_threads) == (0, [], 0)
    assert loaded.vad_threshold == 1.0 and isinstance(loaded.vad_threshold, float)
    assert (loaded.language, loaded.input_device) == (None, None)


def test_non_object_file_gives_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_save_leaves_no_temporary_file(tmp_path: Path):
    path = tmp_path / "settings.json"
    Settings().save(path)
    Settings(model_key="light").save(path)
    assert Settings.load(path).model_key == "light"
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_out_of_range_choices_fall_back(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"dictation_mode": "always", "theme": "light", "model_key": "huge", "cpu_threads": -2,'
        ' "replacements": [["ok", "OK"], ["seul"]], "hotwords": ["ROCm", 3]}',
        encoding="utf-8",
    )
    loaded = Settings.load(path)
    assert loaded.theme == "light"
    assert (loaded.dictation_mode, loaded.model_key, loaded.cpu_threads) == ("hold", "turbo", 0)
    assert (loaded.replacements, loaded.hotwords) == ([], [])


def test_defaults_are_valid_choices():
    from mywhisper.config import CHOICES

    defaults = Settings()
    for name, allowed in CHOICES.items():
        assert getattr(defaults, name) in allowed, name


def test_export_choices_match_the_exporters():
    from mywhisper import export
    from mywhisper.config import CHOICES

    assert {e.suffix for e in export.exporters()} == CHOICES["default_export"]
