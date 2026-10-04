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
    allow_download: bool = True
    models_dir: str = field(default_factory=lambda: str(default_models_dir()))
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
