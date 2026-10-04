"""Télécharge les modèles une fois, pour un usage ensuite entièrement hors ligne.

Usage : python scripts/download_models.py [turbo|precise ...]
"""

from __future__ import annotations

import sys

from faster_whisper.utils import download_model

from doyoucopy.config import Settings
from doyoucopy.core.models import MODELS


def main(keys: list[str]) -> int:
    models_dir = Settings.load().models_dir
    for key in keys or list(MODELS):
        spec = MODELS[key]
        print(f"{spec.model_name} -> {models_dir}")
        path = download_model(spec.model_name, cache_dir=models_dir)
        print(f"  OK : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
