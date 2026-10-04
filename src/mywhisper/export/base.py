"""Export registry: one Exporter per file suffix, chosen from the target's extension.

Each format module calls register() at import (see export/__init__.py, whose
import order is the order of the export menu). Exporters are pure: segments in,
text or bytes out; writing the file is done here, atomically.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from mywhisper.core.types import Segment


class Exporter(Protocol):
    suffix: str
    label: str

    def render(self, segments: Sequence[Segment], **options) -> str | bytes: ...


_EXPORTERS: dict[str, Exporter] = {}


def register(exporter: Exporter) -> Exporter:
    _EXPORTERS[exporter.suffix] = exporter
    return exporter


def exporters() -> list[Exporter]:
    return list(_EXPORTERS.values())


def export(path: Path, segments: Sequence[Segment], **options) -> None:
    """options: max_chars / max_lines for subtitles; other formats ignore them."""
    exporter = _EXPORTERS.get(path.suffix.lower())
    if exporter is None:
        raise ValueError(f"Format non pris en charge : {path.suffix or '(aucune extension)'}")
    data = exporter.render(segments, **options)
    # Through a temporary file: a failed write never leaves a truncated export behind,
    # nor destroys the file it was meant to replace.
    temporary = path.with_name(path.name + ".tmp")
    try:
        if isinstance(data, bytes):
            temporary.write_bytes(data)
        else:
            temporary.write_text(data, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
