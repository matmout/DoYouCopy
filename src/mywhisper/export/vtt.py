from __future__ import annotations

from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register
from mywhisper.export.srt import srt_timestamp
from mywhisper.export.subtitles import build_cues


class VttExporter:
    suffix = ".vtt"
    label = "Sous-titres WebVTT"

    def render(self, segments: Sequence[Segment]) -> str:
        blocks = [
            f"{srt_timestamp(c.start, '.')} --> {srt_timestamp(c.end, '.')}\n{c.text}\n"
            for c in build_cues(segments)
        ]
        return "WEBVTT\n\n" + "\n".join(blocks)


register(VttExporter())
