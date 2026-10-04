import numpy as np

from mywhisper.audio.recorder import resample


def test_resample_length_and_dtype():
    out = resample(np.zeros(48000, dtype=np.float32), 48000)
    assert out.shape == (16000,)
    assert out.dtype == np.float32


def test_resample_preserves_tone():
    t = np.arange(48000) / 48000
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = resample(tone, 48000)
    peak = np.argmax(np.abs(np.fft.rfft(out)))
    assert abs(peak - 440) <= 1  # 1 s of audio -> 1 Hz bins


def test_resample_noop():
    x = np.ones(10, dtype=np.float32)
    assert resample(x, 16000) is x
