"""Scorciatoie da tastiera standard (§8.6).

Invio = Separa, Esc = Annulla/Indietro, Cmd/Ctrl+O = scegli file.
Sono scorciatoie di finestra, instradate da MainWindow secondo la
schermata visibile: funzionano ovunque stia il focus, anche dopo un
cambio di schermata. I menu a tendina e i dialoghi sono finestre a sé
e tengono i loro Invio/Esc.

QKeySequence.StandardKey.Open diventa Cmd+O su macOS e Ctrl+O altrove:
la convenzione la applica Qt, non questo codice.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget


def install(
    window: QWidget,
    on_open: Callable[[], None],
    on_return: Callable[[], None],
    on_escape: Callable[[], None],
) -> list[QShortcut]:
    bindings = (
        (QKeySequence(QKeySequence.StandardKey.Open), on_open),
        (QKeySequence(Qt.Key.Key_Return), on_return),
        (QKeySequence(Qt.Key.Key_Enter), on_return),  # Invio del tastierino
        (QKeySequence(Qt.Key.Key_Escape), on_escape),
    )
    shortcuts: list[QShortcut] = []
    for sequence, handler in bindings:
        shortcut = QShortcut(sequence, window)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(handler)
        shortcuts.append(shortcut)
    return shortcuts


def click_focused_button(window: QWidget) -> bool:
    """Fuori dalla scelta strumenti Invio preme il pulsante col focus:
    fuori da un QDialog Qt lo farebbe solo con la barra spaziatrice."""
    focused = QApplication.focusWidget()
    if isinstance(focused, QAbstractButton) and window.isAncestorOf(focused):
        if focused.isEnabled() and focused.isVisible():
            focused.click()
            return True
    return False
