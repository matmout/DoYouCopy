"""WebVTT (.vtt) subtitles, same cues as SRT with a dot before the milliseconds."""

from __future__ import annotations

from collections.abc import Sequence

from doyoucopy.core.types import Segment
from doyoucopy.export.base import register
from doyoucopy.export.srt import srt_timestamp
from doyoucopy.export.subtitles import MAX_CHARS, MAX_LINES, build_cues


class VttExporter:
    suffix = ".vtt"
    label = "Sous-titres WebVTT"

    def render(
        self, segments: Sequence[Segment], max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES, **_options
    ) -> str:
        blocks = [
            f"{srt_timestamp(c.start, '.')} --> {srt_timestamp(c.end, '.')}\n{c.text}\n"
            for c in build_cues(segments, max_chars, max_lines)
        ]
        return "WEBVTT\n\n" + "\n".join(blocks)


register(VttExporter())
