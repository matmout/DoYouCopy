from pathlib import Path

import pytest

from mywhisper import export
from mywhisper.core.types import Segment
from mywhisper.export.srt import SrtExporter, srt_timestamp
from mywhisper.export.txt import TxtExporter

SEGMENTS = [Segment(0.0, 2.5, "Bonjour à tous."), Segment(2.5, 3661.0105, "Deuxième phrase.")]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "00:00:00,000"), (2.5, "00:00:02,500"), (3661.0105, "01:01:01,010"), (59.9996, "00:01:00,000"), (-1, "00:00:00,000")],
)
def test_srt_timestamp(seconds, expected):
    assert srt_timestamp(seconds) == expected


def test_srt_render():
    assert SrtExporter().render(SEGMENTS) == (
        "1\n00:00:00,000 --> 00:00:02,500\nBonjour à tous.\n"
        "\n"
        "2\n00:00:02,500 --> 01:01:01,010\nDeuxième phrase.\n"
    )


def test_srt_skips_empty_segments_and_renumbers():
    out = SrtExporter().render([Segment(0, 1, ""), Segment(1, 2, "Texte")])
    assert out.startswith("1\n00:00:01,000")


def test_txt_render():
    assert TxtExporter().render(SEGMENTS) == "Bonjour à tous.\nDeuxième phrase.\n"


def test_export_by_suffix(tmp_path: Path):
    target = tmp_path / "out.SRT"
    export.export(target, SEGMENTS)
    assert target.read_text(encoding="utf-8").startswith("1\n")


def test_export_unknown_suffix(tmp_path: Path):
    with pytest.raises(ValueError):
        export.export(tmp_path / "out.docx", SEGMENTS)
