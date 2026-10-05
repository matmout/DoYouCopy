"""Audio sources of the main window: microphone, computer audio, or both mixed."""

from __future__ import annotations

import numpy as np

from doyoucopy.audio.loopback import LoopbackRecorder
from doyoucopy.audio.recorder import MicRecorder
from doyoucopy.i18n import N_

MIC, SYSTEM, BOTH = "mic", "system", "both"
SOURCES = [(MIC, N_("Micro")), (SYSTEM, N_("Ordinateur")), (BOTH, N_("Les deux"))]  # labels: i18n.tr where shown


def mix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Sum of two 16 kHz tracks, the shorter one padded with silence."""
    n = max(a.size, b.size)
    out = np.zeros(n, dtype=np.float32)
    out[: a.size] += a
    out[: b.size] += b
    return np.clip(out, -1.0, 1.0)


class MixedRecorder:
    """Microphone and computer audio together: both sides of a call.

    The two streams are aligned sample by sample; what one has captured ahead of
    the other waits for the next drain().
    """

    def __init__(self, mic, system) -> None:
        self.mic = mic
        self.system = system
        self._pending = (np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32))

    @property
    def device_name(self):
        return self.mic.device_name

    @device_name.setter
    def device_name(self, name) -> None:
        self.mic.device_name = name

    @property
    def is_recording(self) -> bool:
        return self.mic.is_recording

    @property
    def level(self) -> float:
        return max(self.mic.level, self.system.level)

    def start(self) -> None:
        self._pending = (np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32))
        self.mic.start()
        try:
            self.system.start()
        except Exception:
            self.mic.stop()
            raise

    def drain(self) -> np.ndarray:
        a = np.concatenate([self._pending[0], self.mic.drain()])
        b = np.concatenate([self._pending[1], self.system.drain()])
        n = min(a.size, b.size)
        self._pending = (a[n:], b[n:])
        return mix(a[:n], b[:n])

    def stop(self) -> np.ndarray:
        a = np.concatenate([self._pending[0], self.mic.stop()])
        b = np.concatenate([self._pending[1], self.system.stop()])
        self._pending = (np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32))
        return mix(a, b)


def make_recorder(source: str, device_name: str | None = None):
    if source == SYSTEM:
        return LoopbackRecorder()
    if source == BOTH:
        return MixedRecorder(MicRecorder(device_name), LoopbackRecorder())
    return MicRecorder(device_name)
