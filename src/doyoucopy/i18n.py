"""Interface language: French (the language the texts are written in) or English.

Every text shown to the user goes through tr("texte français"): the French text is
the key, and locales/en.py maps it to its English version. A text missing from the
catalog is shown in French, so a forgotten translation never breaks a window
(tests/test_i18n.py checks that none is missing).

The language is chosen once, at startup (setting ui_language, "auto" = the language
of Windows); a change in the settings applies at the next start.

Module-level constants are evaluated at import, before the language is set: mark
them with N_() (so that the test finds them) and translate them where they are
shown, with tr().
"""

from __future__ import annotations

import locale
import logging
import sys

log = logging.getLogger(__name__)

FRENCH, ENGLISH = "fr", "en"
LANGUAGES = (FRENCH, ENGLISH)
# Setting values offered in the settings window; each language in its own name
# (never translated), "auto" = the language of Windows.
CHOICES = (("auto", "Système"), (FRENCH, "Français"), (ENGLISH, "English"))



class _State:
    def __init__(self) -> None:
        self.language = FRENCH
        self.catalog: dict[str, str] = {}  # French text -> translation; empty in French


_state = _State()
_qt_translators: list = []  # kept alive: Qt does not own them


def N_(text: str) -> str:  # the usual name of the gettext no-op marker
    """Marks a text to translate later, with tr(): a module-level constant."""
    return text


def tr(text: str) -> str:
    """The text in the interface language. Placeholders ({name}) are kept: format after."""
    return _state.catalog.get(text, text)


def trn(singular: str, plural: str, count: int) -> str:
    """The singular or plural form for count (French: 0 and 1 are singular)."""
    one = count <= 1 if _state.language == FRENCH else count == 1
    return tr(singular if one else plural)


def number(value: float, decimals: int = 1) -> str:
    """A decimal number written the way the interface language writes it (1,5 / 1.5)."""
    return decimal(f"{value:.{decimals}f}")


def decimal(text: str) -> str:
    """A number already formatted by Python ("0.75"), with the decimal comma in French."""
    return text.replace(".", ",") if _state.language == FRENCH else text


def language() -> str:
    return _state.language


def set_language(code: str) -> None:
    """code: "fr" or "en" (anything else: English)."""
    _state.language = code if code in LANGUAGES else ENGLISH
    if _state.language == ENGLISH:
        from doyoucopy.locales.en import EN

        _state.catalog = EN
    else:
        _state.catalog = {}


def resolve(setting: str | None) -> str:
    """The language for the ui_language setting: "fr", "en", or "auto" (Windows)."""
    return setting if setting in LANGUAGES else system_language()


def system_language() -> str:
    """French if Windows (or the system locale elsewhere) is in French, English otherwise."""
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return FRENCH if lang_id & 0x3FF == 0x0C else ENGLISH  # LANG_FRENCH
        except (AttributeError, OSError):
            log.warning("Could not read the Windows display language")
    name = locale.getlocale()[0] or ""
    return FRENCH if name.lower().startswith("fr") else ENGLISH


def install_qt_translator(app):
    """Qt's own texts (OK / Cancel / Yes / No, file dialogs, context menus) in the
    interface language. Without it they follow the Windows language instead.
    Returns the installed QTranslator, or None if Qt has no translation for it."""
    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator(app)
    folder = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(f"qtbase_{_state.language}", folder):
        log.info("No Qt translation qtbase_%s in %s", _state.language, folder)
        return None
    app.installTranslator(translator)
    _qt_translators.append(translator)
    return translator
