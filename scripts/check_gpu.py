"""Diagnostic de l'accélération ROCm pour faster-whisper.

Usage : python scripts/check_gpu.py [--model tiny] [--no-model]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="tiny", help="modèle de test (défaut : tiny)")
    parser.add_argument("--no-model", action="store_true", help="ne charge aucun modèle")
    args = parser.parse_args()

    print(f"Python        : {sys.version.split()[0]} ({sys.executable})")

    import ctranslate2

    print(f"CTranslate2   : {ctranslate2.__version__} ({os.path.dirname(ctranslate2.__file__)})")
    rocm_runtime = importlib.util.find_spec("_rocm_sdk_core") is not None
    print(f"Runtime ROCm  : {'présent' if rocm_runtime else 'ABSENT'}")

    # The HIP build of CTranslate2 exposes AMD GPUs through the "cuda" device.
    count = ctranslate2.get_cuda_device_count()
    print(f"GPU HIP       : {count}")
    if count == 0:
        print(
            "\nAucun GPU détecté. Vérifiez le pilote Adrenalin et que la wheel ctranslate2 "
            "installée est bien la build ROCm (relancez scripts/install_rocm.ps1).",
            file=sys.stderr,
        )
        return 1
    print(f"Types calcul  : {sorted(ctranslate2.get_supported_compute_types('cuda'))}")

    if args.no_model:
        return 0

    import numpy as np
    from faster_whisper import WhisperModel

    start = time.perf_counter()
    model = WhisperModel(args.model, device="cuda", compute_type="float16")
    print(f"Chargement    : {args.model} en {time.perf_counter() - start:.1f} s")

    t = np.arange(16000 * 5) / 16000
    audio = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    start = time.perf_counter()
    segments, _ = model.transcribe(audio, language="en", vad_filter=False)
    list(segments)
    print(f"Inférence     : 5 s d'audio en {time.perf_counter() - start:.2f} s")
    print("\nOK : faster-whisper tourne sur le GPU via ROCm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
