"""Microphone captures kept next to the history, in FLAC (lossless, ~3 times smaller than WAV)."""

from __future__ import annotations

import logging
import os
import wave
from pathlib import Path

import numpy as np

from mywhisper.core.types import SAMPLE_RATE

log = logging.getLogger(__name__)

FRAME = 4096


def _pcm16(samples: np.ndarray) -> np.ndarray:
    if samples.dtype == np.int16:
        return samples
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)


def write_audio(path: Path, samples: np.ndarray) -> Path:
    """Writes 16 kHz mono samples (float32 or int16) to path (.flac); falls back to .wav.

    The file appears under its final name only once complete (written to .part first),
    so a reader never opens a half-written file. Returns the path actually written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = _pcm16(samples)
    try:
        return _publish(path, _write_flac, pcm)
    except Exception:
        log.exception("FLAC encoding failed, keeping the audio as WAV")
        return _publish(path.with_suffix(".wav"), _write_wav, pcm)


def _publish(path: Path, writer, pcm: np.ndarray) -> Path:
    part = path.with_name(path.name + ".part")
    try:
        writer(part, pcm)
        os.replace(part, path)
    finally:
        part.unlink(missing_ok=True)
    return path


def _write_flac(path: Path, pcm: np.ndarray) -> None:
    import av

    with av.open(str(path), "w", format="flac") as out:
        stream = out.add_stream("flac", rate=SAMPLE_RATE, layout="mono")
        for start in range(0, len(pcm), FRAME):
            frame = av.AudioFrame.from_ndarray(pcm[None, start : start + FRAME], format="s16", layout="mono")
            frame.sample_rate = SAMPLE_RATE
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)


def _write_wav(path: Path, pcm: np.ndarray) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())
