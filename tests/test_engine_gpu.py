"""End-to-end check on the real GPU. Run with: pytest -m gpu"""

import subprocess
import sys
from pathlib import Path

import pytest

from mywhisper.config import Settings
from mywhisper.core.engine import FasterWhisperEngine
from mywhisper.core.models import MODELS
from mywhisper.core.types import TranscribeOptions
from mywhisper.gpu.rocm_env import gpu_device

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(sys.platform != "win32", reason="uses Windows speech synthesis"),
]

PHRASE = "The quick brown fox jumps over the lazy dog."


@pytest.fixture(scope="module")
def speech_wav(tmp_path_factory) -> Path:
    """Synthesises a sample with Windows SAPI so the repo needs no audio fixture."""
    path = tmp_path_factory.mktemp("audio") / "speech.wav"
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{PHRASE}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    return path


@pytest.fixture(scope="module")
def engine() -> FasterWhisperEngine:
    device = gpu_device()
    if device is None:
        pytest.fail("No ROCm GPU detected")
    return FasterWhisperEngine(device, Path(Settings.load().models_dir), cpu_fallback=False)


def test_turbo_transcribes_on_gpu(engine, speech_wav):
    engine.load(MODELS["turbo"])
    assert engine.device.is_gpu
    info, segments = engine.transcribe(speech_wav, TranscribeOptions(language="en"))
    text = " ".join(s.text for s in segments).lower()
    assert info.duration > 1
    for word in ("quick", "brown", "fox", "lazy", "dog"):
        assert word in text
