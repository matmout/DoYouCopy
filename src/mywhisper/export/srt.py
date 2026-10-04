from __future__ import annotations

from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register
from mywhisper.export.subtitles import MAX_CHARS, MAX_LINES, build_cues


def srt_timestamp(seconds: float, separator: str = ",") -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{ms:03d}"


class SrtExporter:
    suffix = ".srt"
    label = "Sous-titres SRT"

    def render(
        self, segments: Sequence[Segment], max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES, **_options
    ) -> str:
        blocks = [
            f"{i}\n{srt_timestamp(c.start)} --> {srt_timestamp(c.end)}\n{c.text}\n"
            for i, c in enumerate(build_cues(segments, max_chars, max_lines), start=1)
        ]
        return "\n".join(blocks)


register(SrtExporter())
