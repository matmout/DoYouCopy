"""End-to-end check on the real GPU. Run with: pytest -m gpu"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mywhisper.config import Settings
from mywhisper.core.engine import FasterWhisperEngine
from mywhisper.core.models import MODELS
from mywhisper.core.types import SAMPLE_RATE, TranscribeOptions
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


def test_live_transcription_on_gpu(engine, speech_wav):
    import time

    from faster_whisper.audio import decode_audio

    from mywhisper.core.live import LiveTranscriber

    engine.load(MODELS["turbo"])
    audio = decode_audio(str(speech_wav))
    audio = np.concatenate([audio, np.zeros(SAMPLE_RATE, dtype=np.float32)])  # trailing pause
    live = LiveTranscriber(engine, TranscribeOptions(language="en"))
    committed, passes = [], []
    chunk = SAMPLE_RATE // 2
    for i in range(0, audio.size, chunk):
        live.feed(audio[i : i + chunk])
        if live.ready():
            start = time.perf_counter()
            committed += live.step().committed
            passes.append(time.perf_counter() - start)
    committed += live.flush().committed

    text = " ".join(s.text for s in committed).lower()
    print(f"\nlive: {len(passes)} passes, mean {sum(passes) / len(passes):.3f} s -> {text!r}")
    for word in ("quick", "brown", "fox", "lazy", "dog"):
        assert word in text
    assert all(a.end <= b.start + 0.5 for a, b in zip(committed, committed[1:]))


def test_batched_inference_and_advanced_options_on_gpu(engine, speech_wav):
    engine.load(MODELS["turbo"])
    options = TranscribeOptions(
        language="en",
        batch_size=8,
        word_timestamps=True,
        hallucination_silence_s=2.0,
        beam_size=3,
        condition_on_previous_text=False,
        vad_threshold=0.4,
        repetition_penalty=1.1,
        initial_prompt="A sentence about a fox and a dog.",
    )
    _, segments = engine.transcribe(speech_wav, options)
    segments = list(segments)
    text = " ".join(s.text for s in segments).lower()
    assert "fox" in text and "dog" in text
    assert segments[0].words  # word timestamps survive the batched path


def test_switch_to_cpu_and_back(engine, speech_wav):
    from mywhisper.gpu.rocm_env import cpu_device

    gpu = engine.device
    engine.configure(device=cpu_device("int8"), cpu_threads=4)
    engine.load(MODELS["turbo"])
    assert not engine.device.is_gpu
    _, segments = engine.transcribe(speech_wav, TranscribeOptions(language="en"))
    assert "fox" in " ".join(s.text for s in segments).lower()
    engine.configure(device=gpu)
    engine.load(MODELS["turbo"])
    assert engine.device.is_gpu
