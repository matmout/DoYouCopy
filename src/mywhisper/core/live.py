"""Live transcription: re-transcribes a sliding audio window and commits stable words.

Whisper has no native streaming. This follows whisper_streaming's LocalAgreement-2
policy (Macháček et al., 2023): each pass transcribes the audio buffer with word
timestamps, and the longest common word prefix of two consecutive passes is
committed. Committed words are recognised in later passes by their timestamps
and dropped, so the buffer only needs cutting at safe points: a pause found by
Silero VAD, or a Whisper segment boundary once the buffer grows long. Cutting at
an estimated word end instead leaves word fragments that get transcribed twice.
"""

from __future__ import annotations

import logging
import re
from itertools import pairwise
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

import numpy as np

from mywhisper.core.engine import TranscriptionEngine
from mywhisper.core.types import SAMPLE_RATE, Segment, TranscribeOptions, Word

log = logging.getLogger(__name__)

# Returns speech regions of 16 kHz audio as (start, end) in seconds.
SpeechDetector = Callable[[np.ndarray], list[tuple[float, float]]]

SENTENCE_END = (".", "?", "!", "…")


def silero_speech(audio: np.ndarray) -> list[tuple[float, float]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    options = VadOptions(min_speech_duration_ms=150, min_silence_duration_ms=300, speech_pad_ms=100)
    return [
        (r["start"] / SAMPLE_RATE, r["end"] / SAMPLE_RATE)
        for r in get_speech_timestamps(audio, options)
    ]


def _norm(text: str) -> str:
    return re.sub(r"[^\w']", "", text.lower())


def words_text(words: Sequence[Word]) -> str:
    return "".join(w.text for w in words).strip()


@dataclass(frozen=True)
class LiveConfig:
    min_step_s: float = 1.0  # new audio needed before a pass
    # Words ending this close to the buffer end stay provisional: Whisper tends to
    # "complete" a sentence it has not heard yet, squeezing timestamps at the edge.
    commit_margin_s: float = 0.3
    endpoint_silence_s: float = 0.8  # trailing silence that ends an utterance
    max_buffer_s: float = 15.0  # past this, cut at the last committed segment boundary
    lead_in_s: float = 0.3  # audio kept before the first detected speech
    prompt_chars: int = 200  # committed text passed as initial_prompt


@dataclass
class LiveUpdate:
    committed: list[Segment] = field(default_factory=list)  # new words, absolute timestamps
    provisional: str = ""


class LiveTranscriber:
    def __init__(
        self,
        engine: TranscriptionEngine,
        options: TranscribeOptions,
        config: LiveConfig | None = None,
        speech_detector: SpeechDetector = silero_speech,
    ) -> None:
        self._engine = engine
        # VAD is handled here; word timestamps drive the agreement.
        self._options = replace(options, vad_filter=False, word_timestamps=True)
        self._config = config or LiveConfig()
        self._detect = speech_detector
        self._buffer = np.zeros(0, dtype=np.float32)
        self._offset = 0.0  # absolute time of _buffer[0]
        self._pending = 0  # samples fed since the last pass
        self._previous: list[Word] = []  # uncommitted words of the last pass
        self._committed: list[Word] = []
        self._committed_end = 0.0

    @property
    def buffer_seconds(self) -> float:
        return self._buffer.size / SAMPLE_RATE

    @property
    def _buffer_end(self) -> float:
        return self._offset + self.buffer_seconds

    def feed(self, samples: np.ndarray) -> None:
        if samples.size:
            self._buffer = np.concatenate([self._buffer, samples.astype(np.float32, copy=False)])
            self._pending += samples.size

    def ready(self) -> bool:
        return self._pending >= self._config.min_step_s * SAMPLE_RATE

    def step(self) -> LiveUpdate | None:
        if not self.ready():
            return None
        self._pending = 0
        speech = [(self._offset + s, self._offset + e) for s, e in self._detect(self._buffer)]
        if not speech:
            # Silence only: keep a short tail so the next word's onset is not cut.
            self._cut_to(self._buffer_end - self._config.lead_in_s)
            self._previous = []
            return LiveUpdate()

        self._cut_to(speech[0][0] - self._config.lead_in_s)
        speech_end = speech[-1][1]
        segments, words = self._transcribe()

        if self._buffer_end - speech_end >= self._config.endpoint_silence_s:
            # Pause: the utterance is over, commit everything and drop its audio.
            update = self._commit(words)
            self._previous = []
            self._cut_to(speech_end)
            return update

        edge = self._buffer_end - self._config.commit_margin_s
        agreed = 0
        for before, now in zip(self._previous, words, strict=False):  # the passes differ in length
            if _norm(before.text) != _norm(now.text) or now.end > edge:
                break
            agreed += 1
        update = self._commit(words[:agreed])
        self._previous = words[agreed:]
        update.provisional = words_text(self._previous)

        self._cut_at_pause(speech)
        if self.buffer_seconds > self._config.max_buffer_s:
            self._trim(segments)
        return update

    def flush(self) -> LiveUpdate:
        """Final pass when the user stops: commits whatever speech remains."""
        update = LiveUpdate()
        if self._buffer.size and self._detect(self._buffer):
            _, words = self._transcribe()
            update = self._commit(words)
        self._cut_to(self._buffer_end)
        self._previous = []
        self._pending = 0
        return update

    # ---- internals ----------------------------------------------------

    def _transcribe(self) -> tuple[list[Segment], list[Word]]:
        before = [w for w in self._committed if w.end <= self._offset + 0.01]
        prompt = words_text(before)[-self._config.prompt_chars :].strip() or None
        _, generated = self._engine.transcribe(
            self._buffer, replace(self._options, initial_prompt=prompt)
        )
        raw = list(generated)
        segments = [
            Segment(self._offset + s.start, self._offset + s.end, s.text) for s in raw if s.text
        ]
        words = [
            Word(self._offset + w.start, self._offset + w.end, w.text)
            for s in raw
            for w in s.words
        ]
        return segments, self._new_words(words)

    def _new_words(self, words: list[Word]) -> list[Word]:
        """Drops words already committed: by timestamp, then by n-gram overlap at the seam."""
        words = [w for w in words if w.start > self._committed_end - 0.1]
        if words and self._committed and abs(words[0].start - self._committed_end) < 1.0:
            for n in range(min(5, len(self._committed), len(words)), 0, -1):
                tail = [_norm(w.text) for w in self._committed[-n:]]
                if tail == [_norm(w.text) for w in words[:n]]:
                    return words[n:]
        return words

    def _commit(self, words: list[Word]) -> LiveUpdate:
        if not words:
            return LiveUpdate()
        self._committed.extend(words)
        self._committed_end = words[-1].end
        return LiveUpdate([Segment(words[0].start, words[-1].end, words_text(words), tuple(words))])

    def _cut_at_pause(self, speech: list[tuple[float, float]]) -> None:
        """Cuts in the middle of the latest pause whose preceding speech is all committed."""
        pending_start = self._previous[0].start if self._previous else float("inf")
        for (_, gap_start), (gap_end, _) in reversed(list(pairwise(speech))):
            if self._committed_end >= gap_start - 0.2 and pending_start >= gap_start - 0.1:
                self._cut_to((gap_start + gap_end) / 2)
                return

    def _trim(self, segments: list[Segment]) -> None:
        """Long utterance without pause: cut at the end of a fully committed segment."""
        boundaries = [s.end for s in segments[:-1] if s.end <= self._committed_end + 0.05]
        self._cut_to(max(boundaries) if boundaries else self._committed_end)

    def _cut_to(self, time: float) -> None:
        samples = int((time - self._offset) * SAMPLE_RATE)
        if samples > 0:
            self._buffer = self._buffer[samples:]
            self._offset += samples / SAMPLE_RATE


def merge_sentences(chunks: Sequence[Segment], max_gap_s: float = 2.5) -> list[Segment]:
    """Regroups live chunks into one segment per sentence, for display and export."""
    words = [w for c in chunks for w in (c.words or (Word(c.start, c.end, " " + c.text),))]
    sentences: list[Segment] = []
    current: list[Word] = []
    for word in words:
        if current and word.start - current[-1].end > max_gap_s:
            sentences.append(_segment(current))
            current = []
        current.append(word)
        if word.text.strip().endswith(SENTENCE_END):
            sentences.append(_segment(current))
            current = []
    if current:
        sentences.append(_segment(current))
    return sentences


def _segment(words: list[Word]) -> Segment:
    return Segment(words[0].start, words[-1].end, words_text(words), tuple(words))
