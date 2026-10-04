from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd

from mywhisper.core.types import SAMPLE_RATE

log = logging.getLogger(__name__)


def list_input_devices() -> list[str]:
    """Input device names for the default host API (avoids MME/WASAPI/WDM duplicates)."""
    host_api = sd.default.hostapi
    return [
        d["name"]
        for d in sd.query_devices()
        if d["max_input_channels"] > 0 and d["hostapi"] == host_api
    ]


def _device_index(name: str | None) -> int | None:
    if not name:
        return None
    for index, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0 and d["hostapi"] == sd.default.hostapi:
            return index
    log.warning("Input device %r not found, using the default one", name)
    return None


def resample(samples: np.ndarray, rate_in: int, rate_out: int = SAMPLE_RATE) -> np.ndarray:
    if rate_in == rate_out or samples.size == 0:
        return samples
    duration = samples.size / rate_in
    x_out = np.linspace(0, duration, int(duration * rate_out), endpoint=False)
    x_in = np.arange(samples.size) / rate_in
    return np.interp(x_out, x_in, samples).astype(np.float32)


class MicRecorder:
    """Records the microphone to 16 kHz mono float32, the format Whisper expects."""

    def __init__(self, device_name: str | None = None) -> None:
        self.device_name = device_name
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._rate = SAMPLE_RATE
        self._level = 0.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """RMS of the last block, 0..1, for a level meter."""
        return self._level

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks = []
        device = _device_index(self.device_name)
        try:
            self._stream = self._open(device, SAMPLE_RATE)
        except sd.PortAudioError:
            # Some drivers refuse 16 kHz: record at the native rate and resample on stop.
            native = int(sd.query_devices(device, "input")["default_samplerate"])
            self._stream = self._open(device, native)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._level = 0.0
        with self._lock:
            chunks, self._chunks = self._chunks, []
        samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return resample(samples, self._rate)

    def _open(self, device: int | None, rate: int) -> sd.InputStream:
        stream = sd.InputStream(
            samplerate=rate, channels=1, dtype="float32", device=device, callback=self._callback
        )
        self._rate = rate
        return stream

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            log.debug("Audio input status: %s", status)
        mono = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
        self._level = min(1.0, float(np.sqrt(np.mean(mono**2))) * 4)
