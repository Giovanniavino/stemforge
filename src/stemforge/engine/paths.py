"""Dove l'app tiene i suoi dati, per piattaforma (BUILD_SPEC §9.2, §10.1).

Un solo posto che conosce le convenzioni di ogni sistema:

- macOS:   ~/Library/Application Support/StemForge
- Windows: %LOCALAPPDATA%\\StemForge — LOCAL e non Roaming: i modelli
  pesano ~1 GB e la calibrazione descrive QUESTA macchina, niente dei
  due deve viaggiare con il profilo utente fra PC diversi
- Linux:   $XDG_DATA_HOME/stemforge (o ~/.local/share/stemforge)

La piattaforma, l'ambiente e la home sono parametri iniettabili: un
test simula un altro sistema passando `platform="win32"`, senza
toccare `sys.platform` né `os.name`. Cambiare `os.name` per tutto il
processo fa creare a pathlib dei WindowsPath su macOS e manda in crash
pytest (visto in CI su macos-15-intel, 09-11-2026).

Le variabili STEMFORGE_MODELS e STEMFORGE_CALIBRATION restano gli
override per i test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


def _context(
    platform: str | None, env: Mapping[str, str] | None, home: Path | None
) -> tuple[str, Mapping[str, str], Path]:
    return (
        sys.platform if platform is None else platform,
        os.environ if env is None else env,
        Path.home() if home is None else home,
    )


def _family(platform: str) -> str:
    """"darwin" | "win32" | "linux": ogni altro Unix segue Linux (XDG)."""
    if platform == "darwin":
        return "darwin"
    if platform in ("win32", "cygwin"):
        return "win32"
    return "linux"


def _local_appdata(env: Mapping[str, str], home: Path) -> Path:
    return Path(env.get("LOCALAPPDATA") or str(home / "AppData" / "Local"))


def data_dir(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform, env, home = _context(platform, env, home)
    family = _family(platform)
    if family == "darwin":
        return home / "Library" / "Application Support" / "StemForge"
    if family == "win32":
        return _local_appdata(env, home) / "StemForge"
    base = env.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(base) / "stemforge"


def log_dir(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Cartella dei log (§10.1 regola 3). Deve coincidere con quella che
    usa ui/app.py, che non può importare engine (§8.5)."""
    platform, env, home = _context(platform, env, home)
    family = _family(platform)
    if family == "darwin":
        return home / "Library" / "Logs" / "StemForge"
    if family == "win32":
        return _local_appdata(env, home) / "StemForge" / "logs"
    return home / ".local" / "state" / "stemforge"


def models_dir(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environ = os.environ if env is None else env
    override = environ.get("STEMFORGE_MODELS")
    if override:
        return Path(override)
    return data_dir(platform, environ, home) / "models"


def calibration_path(
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    environ = os.environ if env is None else env
    override = environ.get("STEMFORGE_CALIBRATION")
    if override:
        return Path(override)
    return data_dir(platform, environ, home) / "calibration.json"
