"""Colori e font dell'app. Un posto solo, nessun colore inline nei widget.

Due temi, chiaro e scuro, scelti dal sistema (§8.6). Ogni coppia testo/
sfondo usata nel foglio di stile rispetta WCAG AA (4.5:1 per il testo,
3:1 per il focus e gli indicatori): lo verifica tests/integration/
test_ui_access.py calcolando i rapporti su questi valori.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    name: str
    background: str
    surface: str
    surface_hover: str
    border: str
    accent: str  # arancio "forgia": sfondo del pulsante principale
    accent_hover: str
    accent_text: str  # accento usato come colore di testo (la stima)
    on_accent: str  # testo sopra l'accento
    selection: str  # riga selezionata, con `text` sopra
    text: str
    text_dim: str
    danger: str
    focus: str  # anello di focus: sempre visibile (§8.6)
    indicator: str  # bordo delle caselle di spunta


DARK = Palette(
    name="dark",
    background="#1b1d22",
    surface="#24272e",
    surface_hover="#2b2f38",
    border="#3a3f4b",
    accent="#e8853b",
    accent_hover="#f09550",
    accent_text="#e8853b",
    on_accent="#14100c",
    selection="#7a4218",
    text="#e8e6e3",
    text_dim="#a9a79f",
    danger="#f07070",
    focus="#f5a462",
    indicator="#8a8f9c",
)

LIGHT = Palette(
    name="light",
    background="#f4f3f0",
    surface="#ffffff",
    surface_hover="#ebe8e3",
    border="#bdb8ae",
    accent="#a94e0b",
    accent_hover="#8f4209",
    accent_text="#a14a0a",
    on_accent="#ffffff",
    selection="#f3d3b8",
    text="#1d1f24",
    text_dim="#5a5852",
    danger="#b3261e",
    focus="#9a4609",
    indicator="#77736b",
)

FONT_FAMILY = "Helvetica Neue, Segoe UI, sans-serif"
MIN_BODY_PT = 10.5  # sotto, il testo è troppo piccolo per molti occhi
TITLE_SCALE = 1.6
ESTIMATE_SCALE = 1.15
_DARK_LIGHTNESS = 128  # sotto questa luminosità la finestra di sistema è scura
_SYSTEM_DARK_PROPERTY = "stemforgeSystemPaletteDark"
_WATCH_PROPERTY = "stemforgeThemeWatch"
_WIN_PERSONALIZE = (
    "HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"
)


def stylesheet(p: Palette, base_pt: float) -> str:
    """Le dimensioni partono dal font di sistema: chi ha ingrandito il
    testo del sistema lo trova ingrandito anche qui (§8.6)."""
    title_pt = round(base_pt * TITLE_SCALE, 1)
    estimate_pt = round(base_pt * ESTIMATE_SCALE, 1)
    return f"""
QWidget {{
    background-color: {p.background};
    color: {p.text};
    font-family: {FONT_FAMILY};
    font-size: {base_pt}pt;
}}
QPushButton {{
    background-color: {p.surface};
    border: 2px solid {p.border};
    border-radius: 6px;
    padding: 7px 15px;
}}
QPushButton:hover {{ background-color: {p.surface_hover}; }}
QPushButton:focus {{ border-color: {p.focus}; }}
QPushButton#primary {{
    background-color: {p.accent};
    color: {p.on_accent};
    font-weight: bold;
    border-color: {p.accent};
}}
QPushButton#primary:hover {{ background-color: {p.accent_hover}; }}
QPushButton#primary:focus {{ border-color: {p.focus}; }}
QPushButton#primary:disabled {{
    background-color: {p.surface};
    color: {p.text_dim};
    border-color: {p.border};
}}
QPushButton#danger {{ color: {p.danger}; }}
QPushButton#danger:focus {{ border-color: {p.focus}; }}
QPushButton#quiet {{ border-color: transparent; color: {p.text_dim}; padding: 4px 8px; }}
QPushButton#quiet:focus {{ border-color: {p.focus}; }}
QCheckBox {{ spacing: 8px; border: 2px solid transparent; border-radius: 4px; padding: 2px 4px; }}
QCheckBox:focus {{ border-color: {p.focus}; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QComboBox {{
    background-color: {p.surface};
    border: 2px solid {p.border};
    border-radius: 6px;
    padding: 3px 9px;
}}
QComboBox:focus {{ border-color: {p.focus}; }}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QProgressBar {{
    background-color: {p.surface};
    border: 1px solid {p.indicator};
    border-radius: 6px;
    text-align: center;
    min-height: 22px;
}}
QProgressBar::chunk {{ background-color: {p.accent}; border-radius: 5px; }}
QListWidget {{
    background-color: {p.surface};
    border: 2px solid {p.border};
    border-radius: 6px;
}}
QListWidget:focus {{ border-color: {p.focus}; }}
QListWidget::item {{ padding: 10px; }}
QListWidget::item:selected {{ background-color: {p.selection}; color: {p.text}; }}
QLabel#title {{ font-size: {title_pt}pt; font-weight: bold; }}
QLabel#dim {{ color: {p.text_dim}; }}
QLabel#estimate {{ font-size: {estimate_pt}pt; color: {p.accent_text}; }}
QLabel#error {{ color: {p.danger}; }}
QFrame#dropzone {{
    background-color: {p.surface};
    border: 2px dashed {p.indicator};
    border-radius: 12px;
}}
QFrame#dropzone[dragActive="true"] {{ border: 3px solid {p.focus}; }}
QToolButton {{ border: 2px solid transparent; border-radius: 4px; font-weight: bold; padding: 2px; }}
QToolButton:focus {{ border-color: {p.focus}; }}
"""


def qt_palette(p: Palette) -> QPalette:
    """Per le parti disegnate dallo stile nativo (menu a tendina,
    caselle, dialoghi di Qt): stessi colori del foglio di stile."""
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, value in (
        (roles.Window, p.background), (roles.WindowText, p.text),
        (roles.Base, p.surface), (roles.AlternateBase, p.surface_hover),
        (roles.Text, p.text), (roles.Button, p.surface),
        (roles.ButtonText, p.text), (roles.Highlight, p.selection),
        (roles.HighlightedText, p.text), (roles.ToolTipBase, p.surface),
        (roles.ToolTipText, p.text), (roles.PlaceholderText, p.text_dim),
        (roles.Link, p.accent_text),
    ):
        palette.setColor(role, QColor(value))
    return palette


def system_prefers_dark(app: QApplication) -> bool:
    """Tema del sistema, con un rilevamento che funziona anche su Qt 6.4.

    QStyleHints.colorScheme esiste da Qt 6.5: sul profilo legacy-intel
    (PySide6 6.4) si ripiega sul registro di Windows e poi sulla
    luminosità della palette di sistema, che su macOS segue l'aspetto.
    """
    scheme_getter = getattr(app.styleHints(), "colorScheme", None)
    if scheme_getter is not None:
        scheme = scheme_getter()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    if sys.platform == "win32":
        light = QSettings(_WIN_PERSONALIZE, QSettings.Format.NativeFormat).value(
            "AppsUseLightTheme"
        )
        if light is not None:
            return str(light) == "0"
    cached = app.property(_SYSTEM_DARK_PROPERTY)
    if isinstance(cached, bool):
        return cached
    window = app.palette().color(QPalette.ColorRole.Window)
    return window.lightness() < _DARK_LIGHTNESS


def base_point_size(app: QApplication) -> float:
    font = app.font()
    size = font.pointSizeF()
    if size <= 0:  # font in pixel: 1 pt = 4/3 px a 96 dpi logici
        size = font.pixelSize() * 0.75
    return max(size, MIN_BODY_PT)


def apply_theme(app: QApplication, palette: Palette | None = None) -> Palette:
    """Applica il tema del sistema (o quello dato) e, dove Qt lo sa
    segnalare (>= 6.5), lo segue quando l'utente lo cambia."""
    if not isinstance(app.property(_SYSTEM_DARK_PROPERTY), bool):
        # la palette di sistema va letta PRIMA di sovrascriverla con la nostra
        window = app.palette().color(QPalette.ColorRole.Window)
        app.setProperty(_SYSTEM_DARK_PROPERTY, window.lightness() < _DARK_LIGHTNESS)
    chosen = palette or (DARK if system_prefers_dark(app) else LIGHT)
    app.setPalette(qt_palette(chosen))
    app.setStyleSheet(stylesheet(chosen, base_point_size(app)))
    _watch_system_scheme(app)
    return chosen


def _watch_system_scheme(app: QApplication) -> None:
    signal = getattr(app.styleHints(), "colorSchemeChanged", None)
    if signal is None or app.property(_WATCH_PROPERTY):
        return
    app.setProperty(_WATCH_PROPERTY, True)
    signal.connect(lambda _scheme: apply_theme(app))
