from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from mywhisper.core.types import Segment


class Exporter(Protocol):
    suffix: str
    label: str

    def render(self, segments: Sequence[Segment]) -> str | bytes: ...


_EXPORTERS: dict[str, Exporter] = {}


def register(exporter: Exporter) -> Exporter:
    _EXPORTERS[exporter.suffix] = exporter
    return exporter


def exporters() -> list[Exporter]:
    return list(_EXPORTERS.values())


def export(path: Path, segments: Sequence[Segment]) -> None:
    exporter = _EXPORTERS.get(path.suffix.lower())
    if exporter is None:
        raise ValueError(f"Format non pris en charge : {path.suffix or '(aucune extension)'}")
    data = exporter.render(segments)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
