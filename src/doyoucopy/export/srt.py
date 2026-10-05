"""SubRip (.srt) subtitles, cut into readable cues by export/subtitles.py."""

from __future__ import annotations

from collections.abc import Sequence

from doyoucopy.core.types import Segment
from doyoucopy.export.base import register
from doyoucopy.export.subtitles import MAX_CHARS, MAX_LINES, build_cues
from doyoucopy.i18n import N_


def srt_timestamp(seconds: float, separator: str = ",") -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{ms:03d}"


class SrtExporter:
    suffix = ".srt"
    label = N_("Sous-titres SRT")

    def render(
        self, segments: Sequence[Segment], max_chars: int = MAX_CHARS, max_lines: int = MAX_LINES, **_options
    ) -> str:
        blocks = [
            f"{i}\n{srt_timestamp(c.start)} --> {srt_timestamp(c.end)}\n{c.text}\n"
            for i, c in enumerate(build_cues(segments, max_chars, max_lines), start=1)
        ]
        return "\n".join(blocks)


register(SrtExporter())
