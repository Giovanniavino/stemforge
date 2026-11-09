"""Verifica che OGNI binario dentro StemForge.app giri sul macOS promesso.

    python packaging/macos/check_min_os.py packaging/dist/StemForge.app 10.15

I runner di CI hanno solo macOS recenti, ma l'app promette 10.15 (Intel)
e 11.0 (Apple Silicon). Ogni file Mach-O dichiara il macOS minimo con cui
è stato compilato (LC_BUILD_VERSION minos, o LC_VERSION_MIN_MACOSX): se
anche una sola libreria del pacchetto chiede di più, su quei Mac l'app
non si apre. Questo controllo lo scopre in CI, senza avere quei Mac.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",  # 32 bit
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",  # 64 bit
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # universale (fat)
}


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in _MACHO_MAGICS
    except OSError:
        return False


def _min_versions(path: Path) -> list[tuple[str, tuple[int, ...]]]:
    """(architettura, macOS minimo) per ogni fetta del binario."""
    output = subprocess.run(
        ["otool", "-arch", "all", "-l", str(path)], capture_output=True, text=True
    ).stdout
    results: list[tuple[str, tuple[int, ...]]] = []
    arch = "?"
    lines = output.splitlines()
    for index, line in enumerate(lines):
        header = re.match(r"^.*\(architecture (\w+)\):$", line)
        if header:
            arch = header.group(1)
        if "LC_BUILD_VERSION" in line or "LC_VERSION_MIN_MACOSX" in line:
            window = "\n".join(lines[index : index + 6])
            match = re.search(r"(?:minos|version)\s+(\d+(?:\.\d+)*)", window)
            platform = re.search(r"platform\s+(\w+)", window)
            if match and (platform is None or platform.group(1) in ("1", "MACOS", "macos")):
                results.append((arch, _version(match.group(1))))
    return results


def main() -> int:
    app = Path(sys.argv[1])
    promised = _version(sys.argv[2])
    offenders: list[str] = []
    checked = 0
    for path in sorted(p for p in app.rglob("*") if p.is_file() and not p.is_symlink()):
        if not _is_macho(path):
            continue
        checked += 1
        for arch, minimum in _min_versions(path):
            if minimum > promised:
                pretty = ".".join(map(str, minimum))
                offenders.append(f"{path.relative_to(app)} [{arch}] richiede macOS {pretty}")
    if offenders:
        print(f"{len(offenders)} binari oltre macOS {sys.argv[2]}:", file=sys.stderr)
        for line in offenders:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"ok: {checked} binari Mach-O, nessuno richiede più di macOS {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
