"""Interface language: the English catalog covers every marked text, and the windows
follow the language chosen at startup."""

import ast
import os
import string
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from doyoucopy import i18n
from doyoucopy.config import Settings
from doyoucopy.gpu.rocm_env import CPU
from doyoucopy.locales.en import EN
from doyoucopy.ui.settings_dialog import SettingsDialog

SRC = Path(__file__).resolve().parents[1] / "src" / "doyoucopy"
MARKERS = {"tr": 1, "N_": 1, "trn": 2}  # function -> number of text arguments


def marked_texts() -> dict[str, str]:
    """Every literal text given to tr(), trn() and N_() in the sources -> where."""
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in MARKERS:
                for arg in node.args[: MARKERS[node.func.id]]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.setdefault(arg.value, f"{path.relative_to(SRC)}:{node.lineno}")
    return found


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


@pytest.fixture(autouse=True)
def french_afterwards():
    yield
    i18n.set_language(i18n.FRENCH)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---- the catalog ------------------------------------------------------------------


def test_every_marked_text_has_an_english_version():
    missing = [f"{where}: {text!r}" for text, where in marked_texts().items() if text not in EN]
    assert not missing, "Add to doyoucopy/locales/en.py:\n" + "\n".join(missing)


def test_no_translation_is_left_unused():
    unused = sorted(set(EN) - set(marked_texts()))
    assert not unused, "No longer in the code, remove from doyoucopy/locales/en.py:\n" + "\n".join(unused)


def test_translations_keep_the_placeholders():
    wrong = [text for text, english in EN.items() if fields(text) != fields(english) or not english.strip()]
    assert not wrong


# ---- tr, trn, number --------------------------------------------------------------


def test_french_by_default():
    assert i18n.language() == i18n.FRENCH
    assert i18n.tr("Fermer") == "Fermer"
    assert i18n.number(1.25, 2) == "1,25"


def test_english_with_fallback_to_french():
    i18n.set_language(i18n.ENGLISH)
    assert i18n.tr("Fermer") == "Close"
    assert i18n.tr("Pas encore traduit") == "Pas encore traduit"  # shown in French, never broken
    assert i18n.tr("Exporté vers {name}").format(name="a.srt") == "Exported to a.srt"
    assert i18n.number(1.25, 2) == "1.25" and i18n.decimal("0.75") == "0.75"


def test_unknown_language_falls_back_to_english():
    i18n.set_language("de")
    assert i18n.language() == i18n.ENGLISH


def test_plural_rules():
    singular, plural = "Direct terminé · {count} phrase", "Direct terminé · {count} phrases"
    assert i18n.trn(singular, plural, 0) == singular  # French: 0 is singular
    assert i18n.trn(singular, plural, 2) == plural
    i18n.set_language(i18n.ENGLISH)
    assert i18n.trn(singular, plural, 0).endswith("sentences")
    assert i18n.trn(singular, plural, 1).format(count=1) == "Live transcription ended · 1 sentence"


def test_resolve_the_setting(monkeypatch):
    assert i18n.resolve("fr") == "fr" and i18n.resolve("en") == "en"
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    assert i18n.resolve("auto") == "en" and i18n.resolve(None) == "en"


@pytest.mark.parametrize(("name", "expected"), [("fr_FR", "fr"), ("fr_CA", "fr"), ("en_US", "en"), (None, "en")])
def test_system_language_outside_windows(monkeypatch, name, expected):
    monkeypatch.setattr(i18n.sys, "platform", "linux")
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (name, "UTF-8"))
    assert i18n.system_language() == expected


def test_system_language_on_windows():
    if os.name != "nt":
        pytest.skip("Windows only")
    assert i18n.system_language() in i18n.LANGUAGES


# ---- the setting ------------------------------------------------------------------


def test_ui_language_setting_roundtrip(tmp_path: Path):
    path = tmp_path / "settings.json"
    assert Settings().ui_language == "auto"
    Settings(ui_language="en").save(path)
    assert Settings.load(path).ui_language == "en"
    path.write_text('{"ui_language": "klingon"}', encoding="utf-8")
    assert Settings.load(path).ui_language == "auto"


# ---- the windows ------------------------------------------------------------------


def test_settings_dialog_in_english_and_restart_offer(app, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    i18n.set_language(i18n.ENGLISH)
    settings = Settings(ui_language="en")
    dialog = SettingsDialog(settings)
    pages = [dialog.nav.item(row).text() for row in range(dialog.nav.count())]
    assert pages[0] == "General" and "Hardware" in pages
    assert not dialog.restart_button.isVisibleTo(dialog)  # already the running language
    combo = dialog.ui_language_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["System", "Français", "English"]
    restarts = []
    dialog.restart_requested.connect(lambda: restarts.append(True))
    combo.setCurrentIndex(combo.findData("fr"))
    assert settings.ui_language == "fr"
    assert dialog.restart_button.isVisibleTo(dialog) and dialog.restart_hint.isVisibleTo(dialog)
    dialog.restart_button.click()
    assert restarts == [True]
    dialog.show_page("Matériel")  # pages are still found by their French key
    assert dialog.pages.currentIndex() == pages.index("Hardware")
    dialog.close()


class _IdleEngine:
    device = CPU
    model = None

    def load(self, spec):
        self.model = spec

    def unload(self):
        self.model = None

    def configure(self, **kwargs):
        self.unload()


def test_main_window_in_english(app, monkeypatch):
    from doyoucopy.ui.main_window import MainWindow
    from doyoucopy.ui.workers import ModelWorker

    monkeypatch.setattr(Settings, "save", lambda self, path=None: None)
    i18n.set_language(i18n.ENGLISH)
    worker = ModelWorker(_IdleEngine())
    window = MainWindow(Settings(), worker, CPU.description)
    try:
        assert window.import_button.text() == "Import a file"
        assert window.copy_button.text() == "Copy" and window.export_button.text() == "Export"
        assert window.language_combo.itemText(0) == "Auto language"
        assert window.transcript.empty.title.text() in ("Ready to transcribe", "")
    finally:
        window.quit_app()
        worker.shutdown()


def test_qt_standard_buttons_follow_the_language(app):
    i18n.set_language(i18n.FRENCH)
    translator = i18n.install_qt_translator(app)
    if translator is None:
        pytest.skip("PySide6 installed without its translations")
    try:
        assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Annuler"
    finally:
        app.removeTranslator(translator)
