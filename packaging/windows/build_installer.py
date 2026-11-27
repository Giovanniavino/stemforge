"""Compila l'installer Windows dall'app già costruita da PyInstaller (§9.7).

    python packaging/windows/build_installer.py [--iscc ISCC.exe]

Un solo comando, uguale in CI e sul dev-box: genera l'icona .ico, misura
il percorso relativo più lungo dentro l'app e lo passa a ISCC insieme
alla versione. Quella misura serve all'installer per rifiutare subito,
con un messaggio chiaro, una cartella in cui non riuscirebbe a scrivere
tutti i file (Inno Setup si ferma oltre MAX_PATH anche con i percorsi
lunghi di Windows attivi) invece di interrompersi a metà copia.

Scrive dist/StemForge-<versione>-windows-x64-setup.exe nella radice del repo.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGING = HERE.parent
ROOT = PACKAGING.parent
ISS_NAME = "stemforge.iss"
_COMPILE_TIMEOUT_S = 30 * 60
# Misurato con ISCC 6.7.2 sul dev-box (cartelle di prova lunghe un carattere
# alla volta): un file la cui cartella supera 259 - 1 - 17 caratteri non si
# crea ("Impossibile trovare il percorso specificato"), qualunque sia il suo
# nome. 17 è la lunghezza del nome temporaneo che Inno usa durante la copia.
INNO_TEMP_NAME_CHARS = 17

sys.path.insert(0, str(HERE))
from make_ico import make_ico  # noqa: E402


def app_version(root: Path = ROOT) -> str:
    """La versione da src/stemforge/__init__.py, senza importare il pacchetto."""
    text = (root / "src" / "stemforge" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    if not match:
        raise ValueError("__version__ assente da src/stemforge/__init__.py")
    return match.group(1)


def longest_relative_path(app: Path) -> int:
    """Caratteri del percorso più lungo che Inno Setup scrive sotto la cartella
    dell'app, separatore iniziale escluso.

    Inno scrive ogni file prima con un nome temporaneo nella sua cartella e
    poi lo rinomina: conta il più lungo fra i due. Inno non sa scrivere oltre
    MAX_PATH nemmeno con i percorsi lunghi di Windows attivi (provato)."""
    lengths = []
    for path in app.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(app)
        folder = len(str(relative.parent)) + 1 if relative.parent.parts else 0
        lengths.append(max(len(str(relative)), folder + INNO_TEMP_NAME_CHARS))
    return max(lengths)


def setup_path(packaging: Path, version: str) -> Path:
    return packaging.parent / "dist" / f"StemForge-{version}-windows-x64-setup.exe"


def compile_installer(iscc: Path, packaging: Path, version: str, defines: dict[str, str] | None = None) -> Path:
    """Compila <packaging>/windows/stemforge.iss contro <packaging>/dist/StemForge.

    `packaging` è la cartella packaging del repo, o una sua copia di prova
    con la stessa struttura (i test usano un'app finta)."""
    app = packaging / "dist" / "StemForge"
    if not (app / "StemForge.exe").is_file():
        raise FileNotFoundError(f"app non costruita: manca {app / 'StemForge.exe'}")
    make_ico(PACKAGING / "icon.png", packaging / "build" / "icon.ico")
    all_defines = {"AppVersion": version, "LongestRelPath": str(longest_relative_path(app)), **(defines or {})}
    command = [str(iscc), "/Q", *(f"/D{k}={v}" for k, v in all_defines.items()), str(packaging / "windows" / ISS_NAME)]
    proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=_COMPILE_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(f"ISCC uscito con {proc.returncode}:\n{proc.stdout}\n{proc.stderr}")
    setup = setup_path(packaging, version)
    if not setup.is_file():
        raise RuntimeError(f"ISCC non ha scritto {setup}")
    return setup


def main() -> int:
    from windows_integration import find_iscc

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iscc", type=Path, default=find_iscc())
    args = parser.parse_args()
    if args.iscc is None:
        print("Inno Setup 6 (ISCC.exe) non trovato: installalo o passa --iscc", file=sys.stderr)
        return 2
    version = app_version()
    setup = compile_installer(args.iscc, PACKAGING, version)
    longest = longest_relative_path(PACKAGING / "dist" / "StemForge")
    print(f"installer: {setup} ({setup.stat().st_size / 2**20:.1f} MiB), versione {version}, "
          f"percorso interno più lungo {longest} caratteri")
    return 0


if __name__ == "__main__":
    sys.exit(main())
