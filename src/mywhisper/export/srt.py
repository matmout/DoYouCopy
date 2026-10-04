from __future__ import annotations

from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register


def srt_timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


class SrtExporter:
    suffix = ".srt"
    label = "Sous-titres SRT"

    def render(self, segments: Sequence[Segment]) -> str:
        blocks = [
            f"{i}\n{srt_timestamp(s.start)} --> {srt_timestamp(s.end)}\n{s.text}\n"
            for i, s in enumerate((s for s in segments if s.text), start=1)
        ]
        return "\n".join(blocks)


register(SrtExporter())
