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
import time
import urllib.request
from importlib import metadata

# Pacchetti che esistono solo sul dev-box Windows: fuori dal lock del Mac.
WINDOWS_ONLY = {"pywin32", "pywin32-ctypes", "pefile", "altgraph"}
# Il pacchetto stesso e gli strumenti di sviluppo non vanno nel lock runtime.
EXCLUDE = {"stemforge", "pip", "setuptools", "wheel", "pyinstaller",
           "pyinstaller-hooks-contrib", "pytest", "iniconfig", "pluggy"}

# Il target (macOS 10.15, Python 3.11) impone versioni diverse dal dev-box:
# PySide6 6.4.3 e' l'ultima Qt che gira su macOS < 11 (BUILD_SPEC §2).
PIN_OVERRIDES = {
    "pyside6": "6.4.3",
    "pyside6-essentials": "6.4.3",
    "pyside6-addons": "6.4.3",
    "shiboken6": "6.4.3",
}

_MAC_TAGS = ("macosx", "universal2", "none-any", "py3-none-any")

# Pacchetti per cui si accetta consapevolmente la build da sorgente sul
# Mac dell'utente. Regola: SOLO Python puro (nessun compilatore coinvolto,
# la build e' un repack di secondi). Roba nativa (il caso sphn di demucs
# 4.1: Rust + CMake + Opus su un Mac del 2012) NON entra qui: si cambia
# versione o dipendenza. Tenere allineato l'elenco con il --no-binary
# dell'installer (Installa StemForge.command).
ALLOW_SDIST_ONLY: set[str] = {
    "antlr4-python3-runtime",  # runtime antlr, puro; sdist-only da sempre
    "demucs",                  # 4.0.1 e' pubblicato solo come sdist, puro
    "dora-search",             # config di demucs, puro, sdist-only
}

_TARGET_CP = 311  # CPython del target (macOS 10.15 -> Python 3.11)


def _relevant(filename: str) -> bool:
    if filename.endswith(".tar.gz") or filename.endswith(".zip"):
        return True  # sdist come riserva accanto alla wheel
    return any(tag in filename for tag in _MAC_TAGS) and "win" not in filename


def _wheel_ok_for_target(filename: str) -> bool:
    """True se la wheel e' installabile su macOS x86_64 / CPython 3.11."""
    if not filename.endswith(".whl"):
        return False
    if filename.endswith("-none-any.whl"):
        return "py3-none" in filename or "py2.py3-none" in filename
    if "macosx" not in filename or not ("x86_64" in filename or "universal2" in filename):
        return False
    if f"cp{_TARGET_CP}" in filename or "py3-none" in filename:
        return True
    # cpXY-abi3: compatibile se compilata per un CPython <= target
    for part in filename.split("-"):
        if part.startswith("cp") and part[2:].isdigit():
            return "abi3" in filename and int(part[2:]) <= _TARGET_CP
    return False


def _files_for(name: str, version: str) -> list[tuple[str, str]]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    last_error: Exception | None = None
    for _ in range(3):  # gli errori di rete transitori non devono bucare il lock
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.load(response)
            return [(e["filename"], e["digests"]["sha256"]) for e in data.get("urls", [])]
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"PyPI irraggiungibile per {name}=={version}: {last_error}")


def main() -> int:
    lines: list[str] = [
        "# requirements-macos-x86_64.lock — generato da packaging/gen_macos_lock.py",
        "# Installare sul Mac Intel con:",
        "#   python3.11 -m pip install --require-hashes -r requirements-macos-x86_64.lock",
        "",
    ]
    missing: list[str] = []
    source_only: list[str] = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        key = name.lower().replace("_", "-")
        if key in EXCLUDE or key in WINDOWS_ONLY:
            continue
        version = PIN_OVERRIDES.get(key, dist.version.split("+")[0])  # 2.2.2+cpu -> 2.2.2
        try:
            files = _files_for(name, version)
        except Exception as exc:  # rete, pacchetto non-PyPI...
            print(f"# ERRORE {name}=={version}: {exc}", file=sys.stderr)
            files = []
        hashes = sorted({h for fn, h in files if _relevant(fn)})
        if not hashes:
            missing.append(f"{name}=={version}")
            continue
        # Guardia anti-sphn: il Mac dell'utente non deve MAI compilare.
        if not any(_wheel_ok_for_target(fn) for fn, _ in files):
            if key not in ALLOW_SDIST_ONLY:
                source_only.append(f"{name}=={version}")
                continue
            print(f"# ATTENZIONE {name}=={version}: solo sdist, build sul Mac", file=sys.stderr)
        entry = f"{name}=={version} " + " \\\n    ".join(
            f"--hash=sha256:{h}" for h in hashes
        )
        lines.append(entry)
    if missing:
        # senza hash il --require-hashes sul Mac fallirebbe: meglio nessun
        # lock che un lock incompleto
        print(
            f"ERRORE: nessun hash ottenuto per: {', '.join(missing)}. "
            "Lock NON generato: riprovare (rete?) o indagare il pacchetto.",
            file=sys.stderr,
        )
        return 1
    if source_only:
        print(
            "ERRORE: pacchetti senza wheel per macOS x86_64 / CPython "
            f"{_TARGET_CP}: {', '.join(source_only)}.\n"
            "Sul Mac dell'utente partirebbe una build da sorgente (vedi il caso "
            "sphn/demucs 4.1). Cambiare versione o dipendenza, non aggirare.",
            file=sys.stderr,
        )
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
