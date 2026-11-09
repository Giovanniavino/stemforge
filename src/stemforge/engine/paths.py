"""Dove l'app tiene i suoi dati, per piattaforma (BUILD_SPEC §9.2).

Un solo posto che conosce le convenzioni di ogni sistema:

- macOS:   ~/Library/Application Support/StemForge
- Windows: %LOCALAPPDATA%\\StemForge — LOCAL e non Roaming: i modelli
  pesano ~1 GB e la calibrazione descrive QUESTA macchina, niente dei
  due deve viaggiare con il profilo utente fra PC diversi
- Linux:   $XDG_DATA_HOME/stemforge (o ~/.local/share/stemforge)

Le variabili STEMFORGE_MODELS e STEMFORGE_CALIBRATION restano gli
override per i test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "StemForge"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "StemForge"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "stemforge"


def models_dir() -> Path:
    override = os.environ.get("STEMFORGE_MODELS")
    if override:
        return Path(override)
    return data_dir() / "models"


def calibration_path() -> Path:
    override = os.environ.get("STEMFORGE_CALIBRATION")
    if override:
        return Path(override)
    return data_dir() / "calibration.json"
