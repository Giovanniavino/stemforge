"""Compila l'installer Windows dall'app già costruita da PyInstaller (§9.7).

    python packaging/windows/build_installer.py [--iscc ISCC.exe]

Un solo comando, uguale in CI e sul dev-box: genera l'icona .ico, misura
il percorso relativo più lungo dentro l'app e lo passa a ISCC insieme
alla versione. Quella misura serve all'installer per rifiutare una
cartella in cui l'app, una volta installata, non potrebbe caricare le sue
DLL (Windows con i percorsi lunghi disattivati, cioè il default).

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
    """Caratteri del percorso più lungo sotto la cartella dell'app, separatore iniziale escluso."""
    return max(len(str(p.relative_to(app))) for p in app.rglob("*"))


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
