"""Plain text export: one line per segment, no times."""

from __future__ import annotations

from collections.abc import Sequence

from doyoucopy.core.types import Segment
from doyoucopy.export.base import register
from doyoucopy.i18n import N_


class TxtExporter:
    suffix = ".txt"
    label = N_("Texte")  # translated where shown

    def render(self, segments: Sequence[Segment], **_options) -> str:
        return "\n".join(s.text for s in segments if s.text) + "\n"


register(TxtExporter())
