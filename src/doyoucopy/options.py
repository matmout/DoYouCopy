"""TranscribeOptions built from the settings, for each use of the model."""

from __future__ import annotations

from doyoucopy.config import Settings
from doyoucopy.core.live import LiveConfig
from doyoucopy.core.types import TranscribeOptions

FILE, LIVE, DICTATION = "file", "live", "dictation"


def transcribe_options(settings: Settings, purpose: str = FILE) -> TranscribeOptions:
    """purpose: "file" (files and recordings), "live" or "dictation"."""
    condition = {"on": True, "off": False}.get(settings.condition_previous)
    return TranscribeOptions(
        language=settings.language,
        # dictation is short and spoken on purpose: the VAD only trims the edges
        vad_filter=settings.vad_filter or purpose == DICTATION,
        word_timestamps=purpose == FILE,  # precise subtitle cuts
        hotwords=settings.hotwords_prompt(),
        initial_prompt=settings.initial_prompt.strip() or None,
        task=settings.task,
        multilingual=settings.multilingual,
        beam_size=settings.beam_size,
        condition_on_previous_text=condition,
        vad_threshold=settings.vad_threshold,
        vad_min_silence_ms=settings.vad_min_silence_ms,
        hallucination_silence_s=2.0 if settings.skip_silence_hallucinations else None,
        no_speech_threshold=settings.no_speech_threshold,
        repetition_penalty=settings.repetition_penalty,
        batch_size=settings.batch_size if purpose == FILE else 0,
    )


def live_config(settings: Settings) -> LiveConfig:
    return LiveConfig(min_step_s=settings.live_step_s, endpoint_silence_s=settings.live_endpoint_s)
