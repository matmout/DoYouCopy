"""JSON export: segments with their words, times and confidence, for other tools."""

from __future__ import annotations

import json
from collections.abc import Sequence

from doyoucopy.core.types import Segment, Word
from doyoucopy.export.base import register


class JsonExporter:
    suffix = ".json"
    label = "JSON (segments et mots)"

    def render(self, segments: Sequence[Segment], **_options) -> str:
        data = {
            "segments": [
                {
                    "start": round(s.start, 3),
                    "end": round(s.end, 3),
                    "text": s.text,
                    "words": [_word(w) for w in s.words],
                }
                for s in segments
                if s.text
            ]
        }
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _word(w: Word) -> dict:
    data = {"start": round(w.start, 3), "end": round(w.end, 3), "text": w.text.strip()}
    if w.probability is not None:
        data["probability"] = round(w.probability, 3)
    return data


register(JsonExporter())
