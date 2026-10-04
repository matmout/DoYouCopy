"""Markdown export: one paragraph per segment, prefixed by its time code."""

from __future__ import annotations

from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register


def timecode(seconds: float) -> str:
    """mm:ss, or h:mm:ss beyond an hour."""
    hours, rest = divmod(int(max(0, seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


class MarkdownExporter:
    suffix = ".md"
    label = "Markdown"

    def render(self, segments: Sequence[Segment], **_options) -> str:
        return "\n\n".join(f"*[{timecode(s.start)}]* {s.text}" for s in segments if s.text) + "\n"


register(MarkdownExporter())
