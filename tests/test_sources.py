import ctypes
import io
import os
import sys
import time
import wave

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from doyoucopy.audio import loopback
from doyoucopy.audio.sources import BOTH, MIC, SYSTEM, MixedRecorder, make_recorder, mix
from doyoucopy.config import Settings
from doyoucopy.core.types import SAMPLE_RATE
from doyoucopy.session import SessionController
from doyoucopy.ui.workers import ModelWorker

from test_ui import FakeEngine


class Source:
    def __init__(self, chunks, level=0.0, fail=False):
        self.chunks = [np.asarray(c, dtype=np.float32) for c in chunks]
        self.level = level
        self.fail = fail
        self.is_recording = False
        self.device_name = None

    def start(self):
        if self.fail:
            raise RuntimeError("pas de sortie audio")
        self.is_recording = True

    def drain(self):
        return self.chunks.pop(0) if self.chunks else np.zeros(0, dtype=np.float32)

    def stop(self):
        self.is_recording = False
        return self.drain()


def test_mix_pads_and_clips():
    out = mix(np.array([0.5, 0.9], dtype=np.float32), np.array([0.25, 0.5, 0.1], dtype=np.float32))
    assert out.tolist() == pytest.approx([0.75, 1.0, 0.1])


def test_mixed_recorder_aligns_both_streams():
    mic = Source([[0.1, 0.1, 0.1], [0.1], [0.1, 0.1]], level=0.2)
    system = Source([[0.2], [0.2, 0.2, 0.2], [0.2]], level=0.6)
    mixed = MixedRecorder(mic, system)
    mixed.device_name = "Micro USB"
    assert mic.device_name == "Micro USB"
    mixed.start()
    assert mixed.is_recording and mixed.level == 0.6
    assert mixed.drain().tolist() == pytest.approx([0.3])  # 3 mic samples, 1 system: one pair ready
    assert mixed.drain().tolist() == pytest.approx([0.3, 0.3, 0.3])
    assert mixed.stop().tolist() == pytest.approx([0.3, 0.1])  # the rest, the shorter padded with silence


def test_mixed_recorder_releases_the_mic_if_the_system_fails():
    mic, system = Source([]), Source([], fail=True)
    with pytest.raises(RuntimeError):
        MixedRecorder(mic, system).start()
    assert not mic.is_recording


def test_make_recorder_by_source():
    assert type(make_recorder(MIC, "x")).__name__ == "MicRecorder"
    assert isinstance(make_recorder(SYSTEM), loopback.LoopbackRecorder)
    both = make_recorder(BOTH, "Micro")
    assert isinstance(both, MixedRecorder) and both.device_name == "Micro"


def test_device_formats():
    fmt = loopback.WAVEFORMATEX(wFormatTag=3, nChannels=2, nSamplesPerSec=48000, wBitsPerSample=32)
    assert ctypes.sizeof(loopback.WAVEFORMATEX) == 18 and ctypes.sizeof(loopback.WAVEFORMATEXTENSIBLE) == 40
    assert loopback.sample_format(fmt, ctypes.addressof(fmt)) == "float32"
    ext = loopback.WAVEFORMATEXTENSIBLE()
    ext.Format = loopback.WAVEFORMATEX(wFormatTag=0xFFFE, nChannels=2, wBitsPerSample=16, cbSize=22)
    ext.SubFormat = loopback.GUID.from_buffer_copy(loopback.SUBTYPE_PCM.bytes_le)
    assert loopback.sample_format(ext.Format, ctypes.addressof(ext)) == "int16"
    with pytest.raises(RuntimeError):
        bad = loopback.WAVEFORMATEX(wFormatTag=2, wBitsPerSample=4)
        loopback.sample_format(bad, ctypes.addressof(bad))
    stereo = np.array([[0.5, -0.5], [1.0, 0.0]], dtype=np.float32).tobytes()
    assert loopback.to_mono_float(stereo, "float32", 2).tolist() == pytest.approx([0.0, 0.5])
    pcm = np.array([[16384, 16384]], dtype=np.int16).tobytes()
    assert loopback.to_mono_float(pcm, "int16", 2).tolist() == pytest.approx([0.5])


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_session_follows_the_source_setting(app):
    made = []

    def factory(source, device):
        made.append((source, device))
        return Source([np.zeros(SAMPLE_RATE)], fail=source == SYSTEM)

    worker = ModelWorker(FakeEngine())
    settings = Settings(audio_source=BOTH, input_device="Micro USB")
    session = SessionController(settings, worker, recorder_factory=factory)
    errors = []
    session.error.connect(lambda message, retry: errors.append(message))
    assert session.start_recording()
    assert made == [(BOTH, "Micro USB")]
    session.recorder.stop()
    settings.audio_source = SYSTEM
    assert not session.start_recording()
    assert errors == ["Impossible de démarrer la capture : pas de sortie audio"]
    worker.shutdown()


@pytest.mark.hardware
@pytest.mark.skipif(sys.platform != "win32", reason="WASAPI")
def test_loopback_captures_what_the_computer_plays():
    import winsound

    rate = 44100
    t = np.arange(int(rate * 1.5)) / rate
    tone = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(tone.tobytes())
    recorder = loopback.LoopbackRecorder()
    recorder.start()
    time.sleep(0.5)
    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)
    time.sleep(0.5)
    audio = recorder.stop()
    assert audio.size == pytest.approx(2.5 * SAMPLE_RATE, rel=0.1)  # silences filled in
    played = audio[int(0.6 * SAMPLE_RATE) : int(1.9 * SAMPLE_RATE)]
    spectrum = np.abs(np.fft.rfft(played))
    assert np.argmax(spectrum) * SAMPLE_RATE / played.size == pytest.approx(440, abs=5)
