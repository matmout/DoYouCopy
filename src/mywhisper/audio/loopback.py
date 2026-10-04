"""What the computer plays (meetings, videos), captured with WASAPI loopback.

PortAudio's Windows build does not expose loopback devices, hence a few COM calls
through ctypes: the default output device is opened in shared loopback mode and
polled from a thread. Windows sends nothing while nothing plays, so the gaps are
filled with silence to keep the timeline in step with the microphone.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
import uuid
from ctypes import POINTER, byref, c_uint32, c_uint64, c_void_p, wintypes

import numpy as np

from mywhisper.audio.recorder import resample

log = logging.getLogger(__name__)

CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioClient = "{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}"
IID_IAudioCaptureClient = "{C8ADBD64-E71E-48A0-A4DE-185C395CD317}"
SUBTYPE_IEEE_FLOAT = uuid.UUID("00000003-0000-0010-8000-00aa00389b71")
SUBTYPE_PCM = uuid.UUID("00000001-0000-0010-8000-00aa00389b71")

E_RENDER, E_CONSOLE = 0, 0
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
SHAREMODE_SHARED = 0
STREAMFLAGS_LOOPBACK = 0x00020000
BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_PCM, WAVE_FORMAT_IEEE_FLOAT, WAVE_FORMAT_EXTENSIBLE = 1, 3, 0xFFFE
BUFFER_100NS = 2_000_000  # 200 ms of buffer in the audio engine
POLL_S = 0.01
FILL_AFTER_S = 0.1  # no packet for this long: nothing plays, write silence
START_TIMEOUT_S = 3.0


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1  # mmreg.h packs the wave formats on one byte
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _pack_ = 1  # mmreg.h packs the wave formats on one byte
    _fields_ = [
        ("Format", WAVEFORMATEX),
        ("wValidBitsPerSample", wintypes.WORD),
        ("dwChannelMask", wintypes.DWORD),
        ("SubFormat", GUID),
    ]


class _Com:
    """A COM interface pointer: methods are called by their vtable index."""

    def __init__(self, pointer: c_void_p) -> None:
        self.ptr = pointer

    def call(self, index: int, *args, argtypes=()):
        vtable = ctypes.cast(self.ptr, POINTER(POINTER(c_void_p)))[0]
        prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
        return prototype(vtable[index])(self.ptr, *args)  # raises OSError on a failed HRESULT

    def release(self) -> None:
        if self.ptr:
            vtable = ctypes.cast(self.ptr, POINTER(POINTER(c_void_p)))[0]
            ctypes.WINFUNCTYPE(wintypes.ULONG, c_void_p)(vtable[2])(self.ptr)
            self.ptr = c_void_p()


def sample_format(fmt: WAVEFORMATEX, address: int) -> str:
    """numpy dtype of the device mix format: "float32", "int16" or "int32"."""
    tag, bits = fmt.wFormatTag, fmt.wBitsPerSample
    if tag == WAVE_FORMAT_EXTENSIBLE:
        sub = uuid.UUID(bytes_le=bytes(WAVEFORMATEXTENSIBLE.from_address(address).SubFormat))
        tag = WAVE_FORMAT_IEEE_FLOAT if sub == SUBTYPE_IEEE_FLOAT else WAVE_FORMAT_PCM if sub == SUBTYPE_PCM else 0
    if tag == WAVE_FORMAT_IEEE_FLOAT and bits == 32:
        return "float32"
    if tag == WAVE_FORMAT_PCM and bits in (16, 32):
        return f"int{bits}"
    raise RuntimeError(f"format audio non pris en charge (type {fmt.wFormatTag}, {bits} bits)")


def to_mono_float(raw: bytes, dtype: str, channels: int) -> np.ndarray:
    samples = np.frombuffer(raw, dtype=dtype).reshape(-1, channels)
    mono = samples.mean(axis=1, dtype=np.float64)
    if dtype == "int16":
        mono /= 32768.0
    elif dtype == "int32":
        mono /= 2147483648.0
    return mono.astype(np.float32)


class LoopbackRecorder:
    """Records the default output device (what you hear), 16 kHz mono float32.

    Same interface as MicRecorder: start(), stop() -> samples, drain(), level.
    """

    device_name = None  # always the default output device

    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._rate = 48000
        self._level = 0.0

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    @property
    def is_recording(self) -> bool:
        return self._thread is not None

    @property
    def level(self) -> float:
        return self._level

    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.available():
            raise RuntimeError("la capture de l'audio de l'ordinateur n'existe que sous Windows")
        self._chunks = []
        self._stop.clear()
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="loopback-capture", daemon=True)
        self._thread.start()
        if not self._ready.wait(START_TIMEOUT_S):
            self._error = RuntimeError("le périphérique de sortie ne répond pas")
        if self._error is not None:
            self._stop.set()
            self._thread.join(1)
            self._thread = None
            raise RuntimeError(f"Audio de l'ordinateur indisponible : {self._error}") from self._error

    def stop(self) -> np.ndarray:
        if self._thread is None:
            return np.zeros(0, dtype=np.float32)
        self._stop.set()
        self._thread.join(2)
        self._thread = None
        self._level = 0.0
        return self.drain()

    def drain(self) -> np.ndarray:
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return resample(np.concatenate(chunks), self._rate)

    # ---- capture thread ------------------------------------------------

    def _append(self, mono: np.ndarray) -> None:
        with self._lock:
            self._chunks.append(mono)

    def _run(self) -> None:
        ole32 = ctypes.OleDLL("ole32")
        ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        enumerator = device = client = capture = None
        mix_format = c_void_p()
        try:
            pointer = c_void_p()
            ole32.CoCreateInstance(
                byref(GUID.of(CLSID_MMDeviceEnumerator)), None, CLSCTX_ALL,
                byref(GUID.of(IID_IMMDeviceEnumerator)), byref(pointer),
            )
            enumerator = _Com(pointer)
            pointer = c_void_p()
            enumerator.call(4, E_RENDER, E_CONSOLE, byref(pointer),
                            argtypes=(ctypes.c_int, ctypes.c_int, POINTER(c_void_p)))  # GetDefaultAudioEndpoint
            device = _Com(pointer)
            pointer = c_void_p()
            device.call(3, byref(GUID.of(IID_IAudioClient)), CLSCTX_ALL, None, byref(pointer),
                        argtypes=(POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p)))  # Activate
            client = _Com(pointer)
            client.call(8, byref(mix_format), argtypes=(POINTER(c_void_p),))  # GetMixFormat
            fmt = WAVEFORMATEX.from_address(mix_format.value)
            dtype, channels, self._rate = sample_format(fmt, mix_format.value), fmt.nChannels, fmt.nSamplesPerSec
            client.call(3, SHAREMODE_SHARED, STREAMFLAGS_LOOPBACK, BUFFER_100NS, 0, mix_format, None,
                        argtypes=(ctypes.c_int, wintypes.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                                  c_void_p, c_void_p))  # Initialize
            pointer = c_void_p()
            client.call(14, byref(GUID.of(IID_IAudioCaptureClient)), byref(pointer),
                        argtypes=(POINTER(GUID), POINTER(c_void_p)))  # GetService
            capture = _Com(pointer)
            client.call(10)  # Start
            log.info("System audio capture: %d Hz, %d channel(s), %s", self._rate, channels, dtype)
            self._ready.set()
            self._loop(capture, dtype, channels, fmt.nBlockAlign)
            client.call(11)  # Stop
        except Exception as exc:
            log.exception("System audio capture failed")
            self._error = exc
            self._ready.set()
        finally:
            for com in (capture, client, device, enumerator):
                if com is not None:
                    com.release()
            plain = ctypes.WinDLL("ole32")  # functions returning void, not an HRESULT
            if mix_format:
                plain.CoTaskMemFree(mix_format)
            plain.CoUninitialize()

    def _loop(self, capture: _Com, dtype: str, channels: int, block_align: int) -> None:
        start = time.perf_counter()
        written = 0  # frames at the device rate since start
        data, frames, flags = POINTER(ctypes.c_ubyte)(), c_uint32(), wintypes.DWORD()
        position, counter, packet = c_uint64(), c_uint64(), c_uint32()
        get_buffer_args = (POINTER(POINTER(ctypes.c_ubyte)), POINTER(c_uint32), POINTER(wintypes.DWORD),
                           POINTER(c_uint64), POINTER(c_uint64))
        while not self._stop.is_set():
            capture.call(5, byref(packet), argtypes=(POINTER(c_uint32),))  # GetNextPacketSize
            while packet.value:
                capture.call(3, byref(data), byref(frames), byref(flags), byref(position), byref(counter),
                             argtypes=get_buffer_args)  # GetBuffer
                count = frames.value
                if flags.value & BUFFERFLAGS_SILENT:
                    mono = np.zeros(count, dtype=np.float32)
                else:
                    mono = to_mono_float(ctypes.string_at(data, count * block_align), dtype, channels)
                capture.call(4, count, argtypes=(c_uint32,))  # ReleaseBuffer
                self._append(mono)
                written += count
                if mono.size:
                    self._level = min(1.0, float(np.sqrt(np.mean(mono**2))) * 4)
                capture.call(5, byref(packet), argtypes=(POINTER(c_uint32),))
            expected = int((time.perf_counter() - start) * self._rate)
            if expected - written > FILL_AFTER_S * self._rate:  # nothing is playing
                gap = expected - written - int(POLL_S * self._rate)
                self._append(np.zeros(gap, dtype=np.float32))
                written += gap
                self._level = 0.0
            self._stop.wait(POLL_S)
