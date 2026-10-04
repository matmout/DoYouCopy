"""Studio theme: design tokens, generated stylesheet, fonts and Windows integration.

Every colour and radius of the UI comes from the tokens below. Rules:
- one accent (signal red, "recording" semantics), nothing else is saturated;
- radii: 12 px containers, 8 px controls, full circle only for the record button;
- depth from surface contrast and hairline borders, no drop shadows.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPalette

log = logging.getLogger(__name__)

FONT_UI = "Geist"
FONT_MONO = "Geist Mono"
RADIUS_CONTAINER = 12
RADIUS_CONTROL = 8
FONTS_DIR = Path(__file__).parent / "resources" / "fonts"


@dataclass(frozen=True)
class Tokens:
    name: str
    bg: str
    surface: str
    elevated: str
    border: str
    text: str
    muted: str
    accent: str
    on_accent: str  # text/icons drawn on the accent

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"

    def qcolor(self, token: str, alpha: float = 1.0) -> QColor:
        color = QColor(getattr(self, token))
        color.setAlphaF(alpha)
        return color


DARK = Tokens(
    name="dark",
    bg="#111214",
    surface="#18191C",
    elevated="#212328",
    border="#2C2F35",
    text="#E9E7E4",
    muted="#8E929B",
    accent="#FF5A47",
    on_accent="#111214",
)

LIGHT = Tokens(
    name="light",
    bg="#F4F4F2",
    surface="#FFFFFF",
    elevated="#ECECEA",
    border="#DADAD6",
    text="#1C1D20",
    muted="#63666D",
    accent="#C8361F",
    on_accent="#FFFFFF",
)


def resolve(setting: str) -> Tokens:
    """setting: "auto" (follow Windows), "dark" or "light"."""
    if setting == "light":
        return LIGHT
    if setting == "dark":
        return DARK
    hints = QGuiApplication.styleHints()
    return LIGHT if hints.colorScheme() == Qt.ColorScheme.Light else DARK


def icon(name: str, t: Tokens, token: str = "text") -> QIcon:
    import qtawesome as qta

    return qta.icon(name, color=getattr(t, token), color_disabled=t.qcolor("muted", 0.5))


def ui_font(size: float = 10.5, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(FONT_UI)
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


def mono_font(size: float = 9.5) -> QFont:
    font = QFont(FONT_MONO)
    font.setPointSizeF(size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def load_fonts() -> None:
    for path in sorted(FONTS_DIR.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(path)) < 0:
            log.warning("Could not load font %s", path.name)


def build_palette(t: Tokens) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.elevated,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.elevated,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.on_accent,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.ToolTipBase: t.elevated,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.Link: t.accent,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, t.qcolor("muted", 0.6))
    return palette


def _check_image(t: Tokens) -> str:
    """QSS cannot draw a tick: render the Phosphor one to a cached PNG, in the theme colour."""
    from PySide6.QtCore import QStandardPaths

    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"check-{t.name}.png"
    icon("ph.check-bold", t, "on_accent").pixmap(28, 28).save(str(path))  # 2x for HiDPI
    return path.as_posix()


def build_qss(t: Tokens) -> str:
    c, r = RADIUS_CONTAINER, RADIUS_CONTROL
    check = _check_image(t)
    return f"""
* {{ font-family: "{FONT_UI}"; outline: none; }}
QMainWindow, #Root {{ background: {t.bg}; }}
QWidget {{ color: {t.text}; }}
QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {t.muted}; }}
QLabel[mono="true"] {{ font-family: "{FONT_MONO}"; color: {t.muted}; }}
QToolTip {{ background: {t.elevated}; color: {t.text}; border: 1px solid {t.border};
           border-radius: {r}px; padding: 4px 8px; }}

#TopBar, #BottomBar {{ background: {t.bg}; }}
#TopBar {{ border-bottom: 1px solid {t.border}; }}
#BottomBar {{ border-top: 1px solid {t.border}; }}
#Wordmark {{ font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }}

QPushButton, QToolButton {{
    background: transparent; color: {t.text}; border: 1px solid transparent;
    border-radius: {r}px; padding: 6px 12px; font-size: 13px;
}}
QPushButton:hover, QToolButton:hover {{ background: {t.elevated}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {t.border}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t.muted}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton[popupMode="1"] {{ padding-right: 18px; }}
QToolButton::menu-button {{ border: none; background: transparent; width: 16px; }}
#IconButton {{ padding: 6px; }}
#LinkButton {{ color: {t.text}; padding: 4px 6px; text-decoration: underline; }}
#LinkButton:hover {{ background: transparent; color: {t.accent}; }}
#LinkButton:disabled {{ color: {t.muted}; text-decoration: none; }}
#OutlineButton {{ border-color: {t.border}; }}
#OutlineButton:hover {{ border-color: {t.accent}; background: transparent; }}

#Segmented {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px; }}
#Segmented QPushButton {{ border-radius: {r - 2}px; padding: 5px 14px; color: {t.muted}; font-weight: 600; }}
#Segmented QPushButton:hover {{ color: {t.text}; background: transparent; }}
#Segmented QPushButton:checked {{ background: {t.accent}; color: {t.on_accent}; }}
#Segmented QPushButton:disabled {{ color: {t.muted}; }}
#Segmented QPushButton:checked:disabled {{ background: {t.border}; color: {t.muted}; }}

QComboBox {{
    background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px;
    padding: 5px 10px; font-size: 13px; min-height: 20px;
}}
QComboBox:hover, QComboBox:focus {{ border-color: {t.muted}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox QAbstractItemView {{
    background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px;
    selection-background-color: {t.border}; selection-color: {t.text}; padding: 4px;
}}

QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QKeySequenceEdit QLineEdit {{
    background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px;
    padding: 5px 8px; font-size: 13px; selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {t.muted}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 16px; border: none; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t.text}; width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; }}
QTableWidget {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px;
    gridline-color: {t.border}; }}
QHeaderView::section {{ background: {t.surface}; color: {t.muted}; border: none; padding: 4px 8px; }}

#SettingsNav {{ background: transparent; border: none; font-size: 13px; outline: none; }}
#SettingsNav::item {{ padding: 8px 12px; border-radius: 6px; margin: 1px 0; }}
#SettingsNav::item:selected {{ background: {t.elevated}; color: {t.text}; }}
#SettingsNav::item:hover:!selected {{ background: {t.surface}; }}
#SettingsPage {{ background: transparent; }}

#HistoryPanel {{ background: {t.bg}; border-right: 1px solid {t.border}; }}
#PanelTitle {{ font-size: 13px; font-weight: 600; }}
#HistoryList {{ background: transparent; border: none; font-size: 12px; outline: none; }}
#HistoryList::item {{ padding: 8px 10px; border-radius: 6px; margin: 1px 0; color: {t.text}; }}
#HistoryList::item:selected {{ background: {t.elevated}; color: {t.text}; }}
#HistoryList::item:hover:!selected {{ background: {t.surface}; }}
#IconButton:checked {{ background: {t.elevated}; border-radius: 6px; }}
#SettingsTitle {{ font-size: 17px; font-weight: 600; }}
#SettingsSection {{ font-size: 11px; color: {t.muted}; font-weight: 600; }}
#SettingsHint {{ font-size: 12px; color: {t.muted}; }}
#SettingsWarning {{ font-size: 12px; color: {t.accent}; }}

QCheckBox {{ spacing: 10px; font-size: 13px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {t.muted}; background: {t.surface};
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url({check}); }}

QMenu {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; font-size: 13px; }}
QMenu::item:selected {{ background: {t.border}; }}

#TranscriptCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {c}px; }}
#TranscriptCard[drag="true"] {{ border: 1px solid {t.accent}; }}
#TranscriptCard QTextEdit {{ background: transparent; border: none; color: {t.text};
    selection-background-color: {t.accent}; selection-color: {t.on_accent}; }}
#EmptyTitle {{ font-size: 15px; font-weight: 500; }}

#Banner {{ background: {t.elevated}; border: 1px solid {t.accent}; border-radius: {c}px; }}
#Banner QLabel {{ font-size: 13px; }}

#ThinProgress {{ background: transparent; border: none; max-height: 2px; }}
#ThinProgress::chunk {{ background: {t.accent}; border-radius: 1px; }}

#Chip {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {r}px;
        padding: 3px 10px; font-family: "{FONT_MONO}"; font-size: 11px; color: {t.muted}; }}
#Chip[accent="true"] {{ border-color: {t.accent}; color: {t.accent}; }}

#Popover {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {c}px; }}
#PopoverTitle {{ font-size: 11px; color: {t.muted}; }}
#Toast {{ background: {t.elevated}; border: 1px solid {t.border}; border-radius: {c}px;
         padding: 10px 14px; font-size: 13px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; height: 0; }}
"""


def apply(app, t: Tokens) -> None:
    app.setPalette(build_palette(t))
    app.setStyleSheet(build_qss(t))


def apply_titlebar(widget, t: Tokens) -> None:
    """Dark native title bar on Windows 10 2004+ / 11, so the window has no white band."""
    if sys.platform != "win32":
        return
    try:
        value = ctypes.c_int(1 if t.is_dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(widget.winId())), 20, ctypes.byref(value), ctypes.sizeof(value)
        )  # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE
    except Exception:
        log.debug("Dark title bar not available", exc_info=True)


def animations_enabled() -> bool:
    """Follows Windows "Show animations" (Settings > Accessibility > Visual effects)."""
    if sys.platform != "win32":
        return True
    try:
        enabled = ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value)  # 0x1042 = SPI_GETCLIENTAREAANIMATION
    except Exception:
        return True


def contrast_ratio(fg: str, bg: str) -> float:
    def luminance(hex_color: str) -> float:
        rgb = QColor(hex_color)
        channels = []
        for v in (rgb.redF(), rgb.greenF(), rgb.blueF()):
            channels.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    lighter, darker = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
