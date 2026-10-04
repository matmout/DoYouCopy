import numpy as np
import pytest

from doyoucopy.core.live import LiveConfig, LiveTranscriber, merge_sentences
from doyoucopy.core.types import SAMPLE_RATE, Segment, TranscribeOptions, TranscriptionInfo, Word


def speech(seconds: float) -> np.ndarray:
    return np.full(round(seconds * SAMPLE_RATE), 0.5, dtype=np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * SAMPLE_RATE), dtype=np.float32)


def energy_detector(audio: np.ndarray) -> list[tuple[float, float]]:
    """Speech = non-zero samples, in 0.1 s frames. Stands in for Silero VAD."""
    frame = SAMPLE_RATE // 10
    regions: list[list[float]] = []
    for i in range(0, audio.size, frame):
        if np.abs(audio[i : i + frame]).max(initial=0) > 0.01:
            start, end = i / SAMPLE_RATE, min(i + frame, audio.size) / SAMPLE_RATE
            if regions and abs(regions[-1][1] - start) < 1e-9:
                regions[-1][1] = end
            else:
                regions.append([start, end])
    return [(s, e) for s, e in regions]


def seg(*words: tuple[float, float, str]) -> Segment:
    ws = tuple(Word(s, e, " " + t) for s, e, t in words)
    return Segment(ws[0].start, ws[-1].end, "".join(w.text for w in ws).strip(), ws)


class ScriptedEngine:
    """Each pass returns the next scripted list of segments (times relative to the buffer)."""

    def __init__(self, *passes: list[Segment]) -> None:
        self.passes = list(passes)
        self.calls: list[tuple[float, TranscribeOptions]] = []

    def transcribe(self, audio, options):
        self.calls.append((audio.size / SAMPLE_RATE, options))
        return TranscriptionInfo("fr", 1.0, audio.size / SAMPLE_RATE), iter(self.passes.pop(0))


def make(engine, **config) -> LiveTranscriber:
    return LiveTranscriber(
        engine, TranscribeOptions(language="fr"), LiveConfig(**config), speech_detector=energy_detector
    )


def texts(update) -> list[str]:
    return [s.text for s in update.committed]


def test_ready_needs_min_step():
    live = make(ScriptedEngine())
    live.feed(speech(0.5))
    assert not live.ready() and live.step() is None
    live.feed(speech(0.5))
    assert live.ready()


def test_words_commit_when_two_passes_agree():
    engine = ScriptedEngine(
        [seg((0.0, 0.4, "Un"), (0.5, 0.9, "deux"))],
        [seg((0.0, 0.4, "Un"), (0.5, 0.9, "deux"), (1.0, 1.5, "trois"))],
        [seg((0.0, 0.4, "Un"), (0.5, 0.9, "deux"), (1.0, 1.5, "trois"), (1.6, 2.0, "quatre"))],
    )
    live = make(engine)
    live.feed(speech(2.0))
    first = live.step()
    assert first.committed == [] and first.provisional == "Un deux"

    live.feed(speech(1.0))
    second = live.step()
    assert texts(second) == ["Un deux"] and second.provisional == "trois"
    assert second.committed[0].words[1] == Word(0.5, 0.9, " deux")

    live.feed(speech(1.0))
    third = live.step()  # "Un deux" are dropped by timestamp, "trois" now agrees
    assert texts(third) == ["trois"] and third.provisional == "quatre"
    options = engine.calls[2][1]
    assert options.word_timestamps and not options.vad_filter


def test_word_at_buffer_edge_stays_provisional():
    engine = ScriptedEngine(
        [seg((0.0, 0.5, "Bonjour"), (0.6, 2.0, "anticipé"))],
        [seg((0.0, 0.5, "Bonjour"), (0.6, 3.0, "anticipé"))],
    )
    live = make(engine)
    live.feed(speech(2.0))
    live.step()
    live.feed(speech(1.0))
    update = live.step()
    assert texts(update) == ["Bonjour"] and update.provisional == "anticipé"


def test_repeated_words_at_the_seam_are_dropped():
    engine = ScriptedEngine(
        [seg((0.0, 0.5, "Il"), (0.5, 1.0, "fait"))],
        [seg((0.0, 0.5, "Il"), (0.5, 1.0, "fait"), (1.1, 1.4, "beau"))],
        # Timestamps drifted: "fait" now starts after the committed end.
        [seg((1.05, 1.3, "fait"), (1.4, 1.7, "beau"), (1.8, 2.2, "aujourd'hui"))],
    )
    live = make(engine)
    for _ in range(3):
        live.feed(speech(1.5))
        update = live.step()
    assert update.provisional == "aujourd'hui"
    assert texts(update) == ["beau"]


def test_pause_commits_everything_and_cuts_there():
    engine = ScriptedEngine([seg((0.0, 0.6, "Phrase"), (0.6, 1.4, "complète."))])
    live = make(engine)
    live.feed(speech(1.5))
    live.feed(silence(1.0))
    update = live.step()
    assert texts(update) == ["Phrase complète."] and update.provisional == ""
    assert live.buffer_seconds == pytest.approx(1.0)


def test_silence_skips_the_model_and_trims_buffer():
    engine = ScriptedEngine()
    live = make(engine)
    live.feed(silence(3.0))
    update = live.step()
    assert update.committed == [] and update.provisional == ""
    assert engine.calls == []
    assert live.buffer_seconds == pytest.approx(0.3)


def test_leading_silence_is_trimmed_and_offset_kept():
    engine = ScriptedEngine([seg((0.0, 1.2, "Bonjour"))])
    live = make(engine)
    live.feed(silence(2.0))
    live.feed(speech(1.3))
    live.feed(silence(1.0))
    update = live.step()
    assert engine.calls[0][0] == pytest.approx(2.6)  # 0.3 s lead-in + 1.3 s speech + 1 s silence
    assert update.committed[0].start == pytest.approx(1.7)


def test_cut_in_a_pause_once_preceding_words_are_committed():
    engine = ScriptedEngine(
        [seg((0.0, 0.9, "Avant")), seg((1.5, 2.0, "après"))],
        [seg((0.0, 0.9, "Avant")), seg((1.5, 2.0, "après"), (2.0, 2.4, "encore"))],
    )
    live = make(engine)
    live.feed(speech(1.0))
    live.feed(silence(0.5))
    live.feed(speech(1.0))
    live.step()
    live.feed(speech(1.0))
    update = live.step()
    assert texts(update) == ["Avant après"]
    assert live.buffer_seconds == pytest.approx(3.5 - 1.25)  # cut mid-pause (1.0..1.5 s)


def test_long_buffer_is_cut_at_a_committed_segment_boundary():
    engine = ScriptedEngine(
        [seg((0.0, 1.0, "A"), (1.0, 2.0, "B")), seg((2.0, 3.0, "C"))],
        [seg((0.0, 1.0, "A"), (1.0, 2.0, "B")), seg((2.0, 3.0, "C"), (3.0, 3.5, "D"))],
    )
    live = make(engine, max_buffer_s=3.0)
    live.feed(speech(3.5))
    live.step()
    live.feed(speech(1.0))
    update = live.step()
    assert texts(update) == ["A B C"]
    assert live.buffer_seconds == pytest.approx(4.5 - 2.0)  # cut after segment "A B"


def test_prompt_holds_only_committed_text_before_the_buffer():
    engine = ScriptedEngine(
        [seg((0.0, 0.9, "Première."))],
        [seg((0.0, 0.5, "Suite"))],
    )
    live = make(engine)
    live.feed(speech(1.0))
    live.feed(silence(1.0))
    live.step()
    live.feed(speech(1.0))
    live.step()
    assert engine.calls[0][1].initial_prompt is None
    assert engine.calls[1][1].initial_prompt == "Première."


def test_flush_commits_remaining_speech():
    engine = ScriptedEngine([seg((0.0, 0.5, "Fin"))])
    live = make(engine)
    live.feed(speech(0.6))
    assert texts(live.flush()) == ["Fin"]
    assert live.buffer_seconds == 0


def test_flush_without_speech_skips_the_model():
    engine = ScriptedEngine()
    live = make(engine)
    live.feed(silence(0.5))
    assert live.flush().committed == [] and engine.calls == []


def test_merge_sentences():
    chunks = [
        seg((0.0, 0.5, "Bonjour."), (1.0, 1.4, "Ceci")),
        seg((1.4, 1.8, "est"), (1.8, 2.3, "un"), (2.3, 2.8, "test.")),
        seg((6.0, 6.5, "Après"), (6.5, 7.0, "pause")),
        seg((10.0, 10.5, "Fin")),
    ]
    merged = merge_sentences(chunks)
    assert [s.text for s in merged] == ["Bonjour.", "Ceci est un test.", "Après pause", "Fin"]
    assert (merged[1].start, merged[1].end) == (1.0, 2.8)
