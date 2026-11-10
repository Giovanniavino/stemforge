"""Convenzioni del sistema operativo (§7.4, §8.6).

Il nome del file manager e del tasto modificatore cambia per sistema:
"Mostra nel Finder" su macOS, "Mostra in Esplora file" su Windows,
"Mostra nella cartella" altrove; Cmd su macOS e Ctrl altrove li scrive
Qt stesso con QKeySequence in formato nativo.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths
from PySide6.QtGui import QKeySequence

translate = QCoreApplication.translate

OUTPUT_FOLDER_NAME = "StemForge"


def reveal_label() -> str:
    if sys.platform == "darwin":
        return translate("Conventions", "Show in Finder")
    if sys.platform == "win32":
        return translate("Conventions", "Show in File Explorer")
    return translate("Conventions", "Show in Folder")


def shortcut_text(sequence: QKeySequence | QKeySequence.StandardKey) -> str:
    """"⌘O" su macOS, "Ctrl+O" altrove, tradotto ("Invio", "Esc")."""
    keys = sequence if isinstance(sequence, QKeySequence) else QKeySequence(sequence)
    return keys.toString(QKeySequence.SequenceFormat.NativeText)


def default_output_dir() -> Path:
    """La cartella Musica vera del sistema + StemForge.

    QStandardPaths chiede al sistema la cartella nota (su Windows
    FOLDERID_Music), quindi rispetta lo spostamento su OneDrive o su un
    altro disco: `~/Music` scritto a mano lì sarebbe sbagliato.
    """
    music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
    base = Path(music) if music else Path.home() / "Music"
    return base / OUTPUT_FOLDER_NAME
