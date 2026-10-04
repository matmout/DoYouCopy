"""Splits segments into subtitle cues that follow the usual broadcast rules:
at most two lines of 42 characters, cut after punctuation when possible."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mywhisper.core.types import Segment

MAX_CHARS = 42
MAX_LINES = 2
BREAK_AFTER = (".", "?", "!", "…", ",", ";", ":")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def build_cues(
    segments: Sequence[Segment], max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES
) -> list[Cue]:
    cues: list[Cue] = []
    for segment in segments:
        tokens = segment.text.split()
        if not tokens:
            continue
        for first, last in _chunks(tokens, max_chars * max_lines):
            start, end = _timing(segment, tokens, first, last)
            cues.append(Cue(start, end, wrap(" ".join(tokens[first:last]), max_chars)))
    return cues


def _chunks(tokens: list[str], limit: int) -> list[tuple[int, int]]:
    """Token ranges [first, last) whose text fits in limit characters."""
    ranges: list[tuple[int, int]] = []
    first, length = 0, 0
    for i, token in enumerate(tokens):
        added = len(token) + (1 if i > first else 0)
        if i > first and length + added > limit:
            cut = _best_break(tokens, first, i, limit)
            ranges.append((first, cut))
            first = cut
            length = len(" ".join(tokens[first : i + 1]))
            continue
        length += added
    ranges.append((first, len(tokens)))
    return ranges


def _best_break(tokens: list[str], first: int, stop: int, limit: int) -> int:
    """Cuts after the last punctuation of the chunk if it leaves the chunk at least half full."""
    for j in range(stop - 1, first, -1):
        if tokens[j - 1].endswith(BREAK_AFTER) and len(" ".join(tokens[first:j])) >= limit // 2:
            return j
    return stop


def _timing(segment: Segment, tokens: list[str], first: int, last: int) -> tuple[float, float]:
    words = segment.words
    if len(words) == len(tokens):
        return words[first].start, words[last - 1].end
    # Text changed after decoding (replacements) or no word timestamps: interpolate on characters.
    text = " ".join(tokens)
    begin = len(" ".join(tokens[:first])) + (1 if first else 0)
    finish = len(" ".join(tokens[:last]))
    span = segment.end - segment.start
    return (
        segment.start + span * begin / len(text),
        segment.start + span * finish / len(text),
    )


def wrap(text: str, max_chars: int = MAX_CHARS) -> tuple[str, ...]:
    """One line, or two lines of balanced length."""
    if len(text) <= max_chars:
        return (text,)
    spaces = [i for i, c in enumerate(text) if c == " "]
    if not spaces:
        return (text,)
    best = min(spaces, key=lambda i: abs(len(text) - 2 * i - 1))
    return (text[:best], text[best + 1 :])
