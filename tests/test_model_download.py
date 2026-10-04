import hashlib
import io
import json

import pytest

from mywhisper.core import model_download
from mywhisper.core.engine import FasterWhisperEngine, ModelNotAvailableError
from mywhisper.core.models import MODELS
from mywhisper.download import DownloadError
from mywhisper.gpu.rocm_env import CPU

REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
MODEL_BIN = b"\x01" * 2_500_000
FILES = {
    "config.json": b"{}",
    "model.bin": MODEL_BIN,
    "tokenizer.json": b"{}",
    "vocabulary.json": b"[]",
    "preprocessor_config.json": b"{}",
    "README.md": b"# not needed",
}


def tree(model_sha=None):
    entries = [{"type": "file", "path": p, "size": len(d)} for p, d in FILES.items() if p != "model.bin"]
    entries.append(
        {
            "type": "file",
            "path": "model.bin",
            "size": 131,
            "lfs": {"oid": model_sha or hashlib.sha256(MODEL_BIN).hexdigest(), "size": len(MODEL_BIN)},
        }
    )
    return json.dumps(entries).encode()


def hub(model_sha=None):
    requested = []

    def opener(url, offset=0):
        requested.append(url)
        if url.endswith("/tree/main"):
            return io.BytesIO(tree(model_sha))
        return io.BytesIO(FILES[url.rsplit("/", 1)[-1]])

    opener.requested = requested
    return opener


def test_download_fetches_only_needed_files_with_progress(tmp_path):
    seen = []
    opener = hub()
    path = model_download.download("large-v3-turbo", tmp_path, lambda d, t: seen.append((d, t)), opener=opener)
    assert path == tmp_path / "large-v3-turbo"
    assert (path / "model.bin").read_bytes() == MODEL_BIN
    assert not (path / "README.md").exists()
    assert model_download.is_complete(path)
    total = sum(len(d) for p, d in FILES.items() if p != "README.md")
    assert seen[-1] == (total, total)
    assert any(REPO in url for url in opener.requested)


def test_download_rejects_a_corrupted_model(tmp_path):
    with pytest.raises(DownloadError, match="SHA-256"):
        model_download.download("large-v3-turbo", tmp_path, opener=hub(model_sha="0" * 64))
    assert not model_download.is_complete(tmp_path / "large-v3-turbo")


def test_engine_reports_download_progress(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        model_download,
        "download",
        lambda name, models_dir, progress: (progress(5, 10), progress(10, 10), tmp_path / name)[-1],
    )
    engine = FasterWhisperEngine(CPU, tmp_path)
    engine.on_download_progress = lambda spec, done, total: calls.append((spec.model_name, done, total))
    assert engine._resolve(MODELS["turbo"]) == str(tmp_path / "large-v3-turbo")
    assert calls == [("large-v3-turbo", 5, 10), ("large-v3-turbo", 10, 10)]


def test_engine_uses_a_complete_local_copy_offline(tmp_path):
    directory = tmp_path / "large-v3-turbo"
    directory.mkdir()
    (directory / "model.bin").write_bytes(b"x")
    (directory / model_download.COMPLETE).write_text(REPO)
    engine = FasterWhisperEngine(CPU, tmp_path, allow_download=False)
    assert engine._resolve(MODELS["turbo"]) == str(directory)
    with pytest.raises(ModelNotAvailableError):
        engine._resolve(MODELS["precise"])


def test_cpu_engine_uses_physical_cores(monkeypatch, tmp_path):
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    assert FasterWhisperEngine(CPU, tmp_path)._threads() == {"cpu_threads": 8}
