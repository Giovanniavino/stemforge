"""Costruisce il pacchetto di installazione per il Mac.

Da Windows non si può cross-compilare un .app: il pacchetto inviabile
contiene i sorgenti, il lock con gli hash e uno script doppio-click che
costruisce l'app NATIVAMENTE sul Mac dell'utente (così macOS non la
blocca come app di sviluppatore sconosciuto).

Uso: python packaging/make_installer.py
Produce: dist/StemForge-Installer.zip
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

# Cosa serve al Mac per costruire l'app: niente test, niente lock Windows.
PROJECT_ITEMS = [
    "pyproject.toml",
    "requirements-macos-x86_64.lock",
    "README.md",
    "BUILD_SPEC.md",
    "packaging/stemforge.spec",
    "packaging/entitlements.plist",
]

_EXEC_MODE = 0o755 << 16  # bit unix nello zip: eseguibile al volo sul Mac


def _add_file(zf: zipfile.ZipFile, source: Path, arcname: str, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arcname)
    info.external_attr = _EXEC_MODE if executable else (0o644 << 16)
    info.compress_type = zipfile.ZIP_DEFLATED
    # \n forzato: gli script sh sul Mac non digeriscono i \r\n di Windows
    data = source.read_bytes().replace(b"\r\n", b"\n") if source.suffix in (
        ".command", ".sh", ".py", ".toml", ".lock", ".md", ".spec", ".plist", ".txt"
    ) else source.read_bytes()
    zf.writestr(info, data)


def main() -> int:
    DIST.mkdir(exist_ok=True)
    target = DIST / "StemForge-Installer.zip"
    with zipfile.ZipFile(target, "w") as zf:
        _add_file(
            zf,
            ROOT / "packaging" / "installer" / "Installa StemForge.command",
            "Installa StemForge.command",
            executable=True,
        )
        _add_file(zf, ROOT / "packaging" / "installer" / "LEGGIMI.txt", "LEGGIMI.txt")
        for item in PROJECT_ITEMS:
            _add_file(zf, ROOT / item, f"StemForge/{item}")
        for source in sorted((ROOT / "src").rglob("*.py")):
            _add_file(zf, source, f"StemForge/{source.relative_to(ROOT).as_posix()}")
    size_mb = target.stat().st_size / 1_000_000
    print(f"creato: {target} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
