import json
import zipfile
from pathlib import Path

import pytest

from doyoucopy import export
from doyoucopy.core.types import Segment, Word
from doyoucopy.export.jsonfmt import JsonExporter
from doyoucopy.export.markdown import MarkdownExporter
from doyoucopy.export.srt import SrtExporter, srt_timestamp
from doyoucopy.export.subtitles import Cue, build_cues, wrap
from doyoucopy.export.txt import TxtExporter
from doyoucopy.export.vtt import VttExporter

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
        export.export(tmp_path / "out.xyz", SEGMENTS)


# ---- subtitles ---------------------------------------------------------

LONG = (
    "Ceci est une phrase assez longue pour dépasser deux lignes de sous-titres, "
    "et elle continue encore un peu plus loin que prévu."
)


def test_wrap_balances_two_lines():
    lines = wrap("Une phrase de taille moyenne qui dépasse quarante-deux caractères")
    assert len(lines) == 2
    assert all(len(line) <= 42 for line in lines)
    assert abs(len(lines[0]) - len(lines[1])) < 10


def test_short_segment_is_one_cue_with_its_timing():
    cues = build_cues([Segment(1.0, 2.0, "Court.")])
    assert cues == [Cue(1.0, 2.0, ("Court.",))]


def test_long_segment_is_split_after_punctuation():
    cues = build_cues([Segment(0.0, 10.0, LONG)])
    assert len(cues) == 2
    assert cues[0].text.replace("\n", " ").endswith("sous-titres,")
    for cue in cues:
        assert len(cue.lines) <= 2 and all(len(line) <= 42 for line in cue.lines)
    # interpolated timing: contiguous, inside the segment
    assert cues[0].start == 0.0 and cues[-1].end == 10.0
    assert cues[0].end <= cues[1].start


def test_cue_timing_uses_word_timestamps():
    tokens = LONG.split()
    words = tuple(Word(i * 0.5, i * 0.5 + 0.4, " " + t) for i, t in enumerate(tokens))
    cues = build_cues([Segment(0.0, 99.0, LONG, words)])
    assert cues[0].start == 0.0
    assert cues[-1].end == words[-1].end
    split = len(cues[0].text.split())
    assert cues[1].start == words[split].start


def test_vtt_render():
    assert VttExporter().render(SEGMENTS[:1]) == "WEBVTT\n\n00:00:00.000 --> 00:00:02.500\nBonjour à tous.\n"


def test_json_render_includes_words():
    seg = Segment(0.0, 1.0, "Salut", (Word(0.0, 1.0, " Salut"),))
    data = json.loads(JsonExporter().render([seg]))
    assert data == {"segments": [{"start": 0.0, "end": 1.0, "text": "Salut", "words": [{"start": 0.0, "end": 1.0, "text": "Salut"}]}]}


def test_markdown_render():
    assert MarkdownExporter().render(SEGMENTS) == "*[00:00]* Bonjour à tous.\n\n*[00:02]* Deuxième phrase.\n"


def test_docx_is_a_valid_zip_with_escaped_text(tmp_path: Path):
    target = tmp_path / "out.docx"
    export.export(target, [Segment(0, 1, "A & B <c>")])
    with zipfile.ZipFile(target) as archive:
        assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= set(archive.namelist())
        document = archive.read("word/document.xml").decode("utf-8")
    assert "A &amp; B &lt;c&gt;" in document


def test_all_formats_registered():
    assert [e.suffix for e in export.exporters()] == [".txt", ".srt", ".vtt", ".md", ".docx", ".json"]
