import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from mywhisper.core.types import Segment, Word  # noqa: E402
from mywhisper.ui import theme  # noqa: E402
from mywhisper.ui.theme import DARK, LIGHT, contrast_ratio  # noqa: E402
from mywhisper.ui.widgets.segmented import SegmentedControl  # noqa: E402
from mywhisper.ui.widgets.transcript_view import TranscriptView  # noqa: E402
from mywhisper.ui.widgets.waveform import WaveformView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=["dark", "light"])
def test_qss_is_fully_resolved(app, tokens):
    qss = theme.build_qss(tokens)
    assert "{t." not in qss and "None" not in qss
    assert qss.count("{") == qss.count("}")
    assert tokens.accent in qss


@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=["dark", "light"])
def test_contrast_meets_wcag_aa(tokens):
    for fg in (tokens.text, tokens.muted, tokens.accent):
        assert contrast_ratio(fg, tokens.surface) >= 4.5, fg
        assert contrast_ratio(fg, tokens.bg) >= 4.5, fg
    assert contrast_ratio(tokens.on_accent, tokens.accent) >= 4.5
    assert contrast_ratio(tokens.muted, tokens.elevated) >= 4.5


def test_bundled_fonts_load(app):
    from PySide6.QtGui import QFontDatabase

    theme.load_fonts()
    families = QFontDatabase.families()
    assert theme.FONT_UI in families and theme.FONT_MONO in families


def test_segmented_control_is_exclusive_and_set_value_is_silent(app):
    control = SegmentedControl([("a", "A"), ("b", "B"), ("c", "C")])
    seen = []
    control.changed.connect(seen.append)
    control.buttons()[2].click()
    assert control.value() == "c" and seen == ["c"]
    assert sum(b.isChecked() for b in control.buttons()) == 1
    control.set_value("a")
    assert control.value() == "a" and seen == ["c"]


def test_waveform_paints_empty_and_full(app):
    view = WaveformView(DARK)
    view.resize(400, 40)
    view.grab()
    view.set_active(True)
    for level in (0.0, 0.3, 1.0, 2.0):
        view.push(level)
    assert not view.grab().isNull()


def test_transcript_live_rendering_replaces_provisional(app):
    view = TranscriptView(DARK)
    word = lambda t, x: Segment(t, t + 0.2, x.strip(), (Word(t, t + 0.2, x),))  # noqa: E731
    view.live_update([word(0, " Bonjour")], "tout le")
    assert view.displayed_text() == "Bonjour tout le"
    view.live_update([word(0.3, " tout"), word(0.5, " le"), word(0.7, " monde.")], "Suite")
    assert view.displayed_text() == "Bonjour tout le monde.\nSuite"
    view.live_update([], "")
    assert view.displayed_text() == "Bonjour tout le monde."
