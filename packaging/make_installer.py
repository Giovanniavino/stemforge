"""Costruisce lo zip di installazione per il Mac mini (BUILD_SPEC §9.5).

Da Windows non si può cross-compilare un .app: lo zip contiene i
sorgenti, i lock con gli hash e due script doppio-click che costruiscono
l'app NATIVAMENTE sul Mac dell'utente (così macOS non la blocca come app
di sviluppatore sconosciuto). Il profilo è legacy-intel (§2).

Se esiste il FFmpeg LGPL già compilato per legacy-intel
(packaging/ffmpeg/out/legacy-intel/ffmpeg, D9) entra nello zip nello
stesso percorso, dove lo spec lo cerca: l'utente non compila mai niente.
Se manca lo zip si fa lo stesso, e l'installer lo dirà a fine
installazione (m4a/aac/alac non supportati).

Uso: python packaging/make_installer.py [--out dist/StemForge-Installer.zip]
"""

from __future__ import annotations

import argparse
import stat
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "dist" / "StemForge-Installer.zip"
FFMPEG_DIR = "packaging/ffmpeg/out/legacy-intel"
INSTALLER_DIR = "packaging/installer"

# Cosa serve al Mac per costruire l'app: niente test, niente lock di altri profili.
REQUIRED_ITEMS = (
    "pyproject.toml",
    "requirements-macos-x86_64.lock",
    "README.md",
    "LICENSE",
    "packaging/stemforge.spec",
    "packaging/entitlements.plist",
    "packaging/icon.png",
    f"{INSTALLER_DIR}/comune.sh",
    f"{INSTALLER_DIR}/requirements-build-macos-x86_64.lock",
)
OPTIONAL_ITEMS = ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.txt")
# in cima allo zip: ciò che l'utente vede appena estratto
TOP_LEVEL = (
    ("Installa StemForge.command", True),
    ("Aggiorna StemForge.command", True),
    ("LEGGIMI.txt", False),
)
# insieme all'eseguibile, gli eventuali testi di licenza dell'area FFmpeg
FFMPEG_NOTICES = ("LICENSE*", "COPYING*", "*.txt", "*.md")
TEXT_SUFFIXES = {".command", ".sh", ".py", ".toml", ".lock", ".md", ".spec", ".plist", ".txt"}
TEXT_NAMES = {"LICENSE"}
_UNIX = 3  # "made by" Unix: senza, Archive Utility e unzip ignorano i permessi
_EXECUTABLE = stat.S_IFREG | 0o755
_REGULAR = stat.S_IFREG | 0o644


class IncompleteSourceError(RuntimeError):
    """Manca un file senza il quale lo zip non installerebbe nulla."""


def _is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES


def add_file(zf: zipfile.ZipFile, source: Path, arcname: str, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arcname)
    info.create_system = _UNIX
    info.external_attr = (_EXECUTABLE if executable else _REGULAR) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    data = source.read_bytes()
    if _is_text(source):
        # \n forzato: sh sul Mac non digerisce i \r\n di un checkout Windows
        data = data.replace(b"\r\n", b"\n")
    zf.writestr(info, data)


def _sources(root: Path) -> Iterator[Path]:
    # tutto il pacchetto, non solo i .py: un dato aggiunto domani deve esserci
    for path in sorted((root / "src" / "stemforge").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            yield path


def _ffmpeg_files(root: Path) -> list[tuple[Path, bool]]:
    folder = root / FFMPEG_DIR
    binary = folder / "ffmpeg"
    if not binary.is_file():
        return []
    notices = {path for pattern in FFMPEG_NOTICES for path in folder.glob(pattern) if path.is_file()}
    return [(binary, True), *((path, False) for path in sorted(notices))]


def _project_files(root: Path) -> list[tuple[Path, bool]]:
    missing = [item for item in REQUIRED_ITEMS if not (root / item).is_file()]
    if missing:
        raise IncompleteSourceError(f"mancano: {', '.join(missing)}")
    # comune.sh si carica con ".", non si esegue: niente bit eseguibile
    files = [(root / item, False) for item in REQUIRED_ITEMS]
    files += [(root / item, False) for item in OPTIONAL_ITEMS if (root / item).is_file()]
    files += [(path, False) for path in sorted((root / "resources" / "i18n").glob("*.qm"))]
    files += [(path, False) for path in _sources(root)]
    return files + _ffmpeg_files(root)


def build_zip(root: Path, target: Path) -> list[Path]:
    """Scrive lo zip; restituisce i file del FFmpeg LGPL inclusi (vuota se manca)."""
    files = _project_files(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as zf:
        for name, executable in TOP_LEVEL:
            add_file(zf, root / INSTALLER_DIR / name, name, executable)
        for source, executable in files:
            add_file(zf, source, f"StemForge/{source.relative_to(root).as_posix()}", executable)
    return [path for path, _ in _ffmpeg_files(root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="zip da creare")
    args = parser.parse_args(argv)
    try:
        ffmpeg = build_zip(ROOT, args.out)
    except IncompleteSourceError as error:
        print(f"ERRORE: sorgenti incompleti, {error}", file=sys.stderr)
        return 1
    size_mb = args.out.stat().st_size / 1_000_000
    print(f"creato: {args.out} ({size_mb:.1f} MB)")
    if ffmpeg:
        print(f"FFmpeg LGPL incluso da {FFMPEG_DIR}: m4a/aac/alac supportati.")
        if len(ffmpeg) == 1 and not any((ROOT / item).is_file() for item in OPTIONAL_ITEMS):
            # LGPL: chi riceve il binario deve ricevere anche avviso e link al sorgente
            print("ATTENZIONE: FFmpeg incluso senza testo di licenza ne' "
                  "THIRD_PARTY_NOTICES: non distribuire questo zip.", file=sys.stderr)
    else:
        print(f"ATTENZIONE: {FFMPEG_DIR}/ffmpeg non c'e': lo zip funziona ma l'app "
              "non aprira' m4a/aac/alac (l'installer lo dira' all'utente).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
