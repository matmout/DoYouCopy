"""User settings: one JSON file in %APPDATA%/MyWhisper, and the app's data folders.

Settings is the single source of truth while the app runs: the window, the
dictation and the engine all read it. The file is only a snapshot of it, written
after every change; a missing, damaged or partly invalid file never prevents the
app from starting (the affected values fall back to their defaults).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from mywhisper.core.models import DEFAULT_MODEL_KEY

log = logging.getLogger(__name__)

# Settings whose default is None but which hold a string once chosen.
_OPTIONAL_STR = {"language", "input_device"}


def _app_dir(env_var: str, fallback: str) -> Path:
    base = os.environ.get(env_var) or str(Path.home() / "AppData" / fallback)
    return Path(base) / "MyWhisper"


def default_settings_path() -> Path:
    return _app_dir("APPDATA", "Roaming") / "settings.json"


def default_history_dir() -> Path:
    override = os.environ.get("MYWHISPER_HISTORY_DIR")
    return Path(override) if override else _app_dir("LOCALAPPDATA", "Local") / "history"


def default_models_dir() -> Path:
    override = os.environ.get("MYWHISPER_MODELS_DIR")
    return Path(override) if override else _app_dir("LOCALAPPDATA", "Local") / "models"


@dataclass
class Settings:
    """Every user choice, with its default. Adding a field is enough to persist it:
    older files simply lack it (default used), unknown keys are ignored."""

    model_key: str = DEFAULT_MODEL_KEY
    language: str | None = None
    vad_filter: bool = True
    show_timestamps: bool = False
    mode: str = "record"  # last capture mode: "record" or "live"
    theme: str = "dark"  # "auto" (follow Windows), "dark" or "light"
    input_device: str | None = None  # device name; indices change between sessions
    audio_source: str = "mic"  # main window captures: "mic", "system" (computer audio) or "both"
    device: str = "auto"  # "auto", "gpu" or "cpu"
    compute_type: str = "auto"  # "auto" or a CTranslate2 type (float16, int8_float16, int8…)
    cpu_threads: int = 0  # 0 = one per physical core
    allow_download: bool = True
    models_dir: str = field(default_factory=lambda: str(default_models_dir()))
    # transcription
    task: str = "transcribe"  # or "translate" (to English)
    multilingual: bool = False
    initial_prompt: str = ""  # context given to the model: topic, names, style
    beam_size: int = 0  # 0 = the model's default
    condition_previous: str = "auto"  # "auto", "on" or "off"
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 500
    skip_silence_hallucinations: bool = True
    no_speech_threshold: float = 0.6
    repetition_penalty: float = 1.0
    batch_size: int = 0  # files: 0 = sequential, 8 / 16 = batched (GPU)
    # live mode
    live_step_s: float = 1.0
    live_endpoint_s: float = 0.8
    # display and exports
    transcript_font_size: int = 12
    subtitle_max_chars: int = 42
    subtitle_max_lines: int = 2
    default_export: str = ".txt"
    # vocabulary
    hotwords: list[str] = field(default_factory=list)
    replacements: list[list[str]] = field(default_factory=list)  # [heard, written] pairs
    voice_commands: bool = True  # spoken punctuation, universal dictation only
    # universal dictation
    dictation_enabled: bool = True
    dictation_hotkey: str = "Ctrl+Shift+Space"
    dictation_mode: str = "hold"  # "hold" (push-to-talk) or "toggle"
    dictation_output: str = "paste"  # "paste" into the active app or "clipboard" only
    dictation_sounds: bool = True
    dictation_trailing_space: bool = True  # successive dictations do not stick together
    close_to_tray: bool = True
    # history
    history_enabled: bool = True
    history_keep_audio: bool = True  # microphone captures, for replay and re-transcription
    history_audio_days: int = 30  # the audio is deleted after N days, the text kept (0 = never)
    history_dictation: bool = True  # also keep the text of universal dictations
    history_visible: bool = False  # side panel shown

    def hotwords_prompt(self) -> str | None:
        words = [w.strip() for w in self.hotwords if w.strip()]
        return ", ".join(words) or None

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        """Reads the file; never raises. Values of the wrong type are dropped one by one."""
        path = path or default_settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.warning("Unreadable settings file %s, using defaults", path)
            return cls()
        if not isinstance(data, dict):
            log.warning("Settings file %s holds no object, using defaults", path)
            return cls()
        defaults = cls()
        values = {}
        for f in fields(cls):
            if f.name in data:
                value = _checked(f.name, data[f.name], getattr(defaults, f.name))
                if value is not _INVALID:
                    values[f.name] = value
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        """Atomic: written to a temporary file, then renamed over the old one, so a crash
        or a full disk mid-write cannot leave a truncated file (and reset every setting)."""
        path = path or default_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)


_INVALID = object()


def _checked(name: str, value, default):
    """value if it has the type of the default (int accepted for a float), else _INVALID.

    Guards against hand-edited or damaged files: a "beam_size": "5" would otherwise
    reach CTranslate2, a "hotwords": null would crash the first transcription."""
    if value is None and (default is None or name in _OPTIONAL_STR):
        return None
    expected = str if default is None else type(default)
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if expected is int and isinstance(value, bool):
        valid = False  # bool is a subclass of int, but True is no thread count
    else:
        valid = isinstance(value, expected)
    if not valid:
        log.warning("Setting %s: invalid value %r ignored, default kept", name, value)
        return _INVALID
    return value
