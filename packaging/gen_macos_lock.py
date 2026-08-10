"""Genera requirements-macos-x86_64.lock con gli hash SHA-256 da PyPI.

BUILD_SPEC §2: il lock del target si fissa con hash. Questo script parte
dalle versioni risolte nel venv di sviluppo, normalizza i pin locali
(+cpu) e interroga PyPI per gli hash dei wheel macOS x86_64 / universal2
/ py3-none-any (più l'sdist come riserva).

Uso: python packaging/gen_macos_lock.py > requirements-macos-x86_64.lock
"""

from __future__ import annotations

import json
import sys
import urllib.request
from importlib import metadata

# Pacchetti che esistono solo sul dev-box Windows: fuori dal lock del Mac.
WINDOWS_ONLY = {"pywin32", "pywin32-ctypes", "pefile", "altgraph"}
# Il pacchetto stesso e gli strumenti di sviluppo non vanno nel lock runtime.
EXCLUDE = {"stemforge", "pip", "setuptools", "wheel", "pyinstaller",
           "pyinstaller-hooks-contrib", "pytest", "iniconfig", "pluggy"}

_MAC_TAGS = ("macosx", "universal2", "none-any", "py3-none-any")


def _relevant(filename: str) -> bool:
    if filename.endswith(".tar.gz") or filename.endswith(".zip"):
        return True  # sdist come riserva
    return any(tag in filename for tag in _MAC_TAGS) and "win" not in filename


def _hashes_for(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
    return sorted(
        {
            entry["digests"]["sha256"]
            for entry in data.get("urls", [])
            if _relevant(entry["filename"])
        }
    )


def main() -> int:
    lines: list[str] = [
        "# requirements-macos-x86_64.lock — generato da packaging/gen_macos_lock.py",
        "# Installare sul Mac Intel con:",
        "#   python3.11 -m pip install --require-hashes -r requirements-macos-x86_64.lock",
        "",
    ]
    missing: list[str] = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        key = name.lower().replace("_", "-")
        if key in EXCLUDE or key in WINDOWS_ONLY:
            continue
        version = dist.version.split("+")[0]  # 2.2.2+cpu -> 2.2.2
        try:
            hashes = _hashes_for(name, version)
        except Exception as exc:  # rete, pacchetto non-PyPI...
            print(f"# ERRORE {name}=={version}: {exc}", file=sys.stderr)
            hashes = []
        if not hashes:
            missing.append(f"{name}=={version}")
            continue
        entry = f"{name}=={version} " + " \\\n    ".join(
            f"--hash=sha256:{h}" for h in hashes
        )
        lines.append(entry)
    if missing:
        lines.append("")
        lines.append("# SENZA HASH SU PYPI (verificare a mano prima del build):")
        for item in missing:
            lines.append(f"# {item}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
