from __future__ import annotations

from collections.abc import Sequence

from mywhisper.core.types import Segment
from mywhisper.export.base import register


class TxtExporter:
    suffix = ".txt"
    label = "Texte"

    def render(self, segments: Sequence[Segment]) -> str:
        return "\n".join(s.text for s in segments if s.text) + "\n"


register(TxtExporter())
