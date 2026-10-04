"""Short cues when the dictation starts and stops, synthesised: no audio file to ship."""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

RATE = 44100
VOLUME = 0.12


def _tone(freqs: tuple[float, ...], note_s: float = 0.06) -> np.ndarray:
    t = np.arange(int(RATE * note_s)) / RATE
    envelope = np.sin(np.pi * t / note_s)  # no click at either end
    notes = [np.sin(2 * np.pi * f * t) * envelope for f in freqs]
    return (np.concatenate(notes) * VOLUME).astype(np.float32)


START = _tone((660.0, 880.0))
STOP = _tone((880.0, 660.0))


def play(samples: np.ndarray) -> None:
    try:
        import sounddevice as sd

        sd.play(samples, RATE)  # non-blocking
    except Exception:
        log.debug("Could not play the dictation cue", exc_info=True)
