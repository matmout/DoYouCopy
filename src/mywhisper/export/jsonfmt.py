from __future__ import annotations

import json
from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register


class JsonExporter:
    suffix = ".json"
    label = "JSON (segments et mots)"

    def render(self, segments: Sequence[Segment]) -> str:
        data = {
            "segments": [
                {
                    "start": round(s.start, 3),
                    "end": round(s.end, 3),
                    "text": s.text,
                    "words": [
                        {"start": round(w.start, 3), "end": round(w.end, 3), "text": w.text.strip()}
                        for w in s.words
                    ],
                }
                for s in segments
                if s.text
            ]
        }
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


register(JsonExporter())
