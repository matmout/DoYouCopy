from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from mywhisper.core.models import DEFAULT_MODEL_KEY

log = logging.getLogger(__name__)


def _app_dir(env_var: str, fallback: str) -> Path:
    base = os.environ.get(env_var) or str(Path.home() / "AppData" / fallback)
    return Path(base) / "MyWhisper"


def default_settings_path() -> Path:
    return _app_dir("APPDATA", "Roaming") / "settings.json"


def default_models_dir() -> Path:
    override = os.environ.get("MYWHISPER_MODELS_DIR")
    return Path(override) if override else _app_dir("LOCALAPPDATA", "Local") / "models"


@dataclass
class Settings:
    model_key: str = DEFAULT_MODEL_KEY
    language: str | None = None
    vad_filter: bool = True
    show_timestamps: bool = False
    mode: str = "record"  # last capture mode: "record" or "live"
    theme: str = "dark"  # "auto" (follow Windows), "dark" or "light"
    input_device: str | None = None  # device name; indices change between sessions
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

    def hotwords_prompt(self) -> str | None:
        words = [w.strip() for w in self.hotwords if w.strip()]
        return ", ".join(words) or None

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or default_settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.warning("Unreadable settings file %s, using defaults", path)
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> None:
        path = path or default_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
