"""Colori e font dell'app. Un posto solo, nessun colore inline nei widget."""

from __future__ import annotations

BACKGROUND = "#1b1d22"
SURFACE = "#24272e"
SURFACE_HOVER = "#2b2f38"
BORDER = "#3a3f4b"
ACCENT = "#e8853b"  # arancio "forgia"
ACCENT_DIM = "#a45f2a"
TEXT = "#e8e6e3"
TEXT_DIM = "#9a9890"
DANGER = "#d05050"

FONT_FAMILY = "Helvetica Neue, Segoe UI, sans-serif"

STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}
QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{ background-color: {SURFACE_HOVER}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    color: #14100c;
    font-weight: bold;
    border: none;
}}
QPushButton#primary:hover {{ background-color: #f09550; }}
QPushButton#primary:disabled {{ background-color: {ACCENT_DIM}; color: #3a2d20; }}
QPushButton#danger {{ border-color: {DANGER}; color: {DANGER}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}
QComboBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 10px;
}}
QProgressBar {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 22px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 5px; }}
QListWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
QListWidget::item {{ padding: 10px; }}
QListWidget::item:selected {{ background-color: {ACCENT_DIM}; color: {TEXT}; }}
QLabel#title {{ font-size: 22px; font-weight: bold; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#estimate {{ font-size: 16px; color: {ACCENT}; }}
QLabel#error {{ color: {DANGER}; }}
QFrame#card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#dropzone {{
    background-color: {SURFACE};
    border: 2px dashed {BORDER};
    border-radius: 12px;
}}
QFrame#dropzone[dragActive="true"] {{ border-color: {ACCENT}; }}
QToolButton {{ border: none; font-weight: bold; }}
"""
