"""Chiude il pacchetto PyInstaller sulle librerie di sistema (BUILD_SPEC §9.8).

    python bundle_libs.py BUNDLE HOST_LIBS [--report FILE]

BUNDLE e' la cartella di PyInstaller (StemForge + _internal/), HOST_LIBS
l'elenco delle librerie che fornisce il sistema (host_libs.txt).

PyInstaller copia le dipendenze che trova, ma non sa quali sono "del
sistema" su un'altra distribuzione: ne prende troppe (libstdc++, la
fontconfig della build) e non segnala quelle che mancano nella build.
Qui, in tre passi:
1. toglie dal pacchetto cio' che deve venire dall'host;
2. aggiunge in _internal/ ogni dipendenza risolta fuori dal pacchetto
   e non dell'host (ripetendo finche' non ne compaiono di nuove);
3. fallisce se una dipendenza non si trova e non e' dell'host: sulla
   macchina dell'utente Qt direbbe solo "could not load plugin".
Le librerie aggiunte o gia' prese dal sistema finiscono nel report, con
il pacchetto rpm e la licenza: servono a THIRD_PARTY_NOTICES (§11.11).

Si lancia nel container di build: `ldd` esegue il loader sui file, che
qui sono i nostri.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"
_MAX_ROUNDS = 10  # ogni giro aggiunge le dipendenze delle aggiunte: 3 bastano
_LDD_LINE = re.compile(r"^\s*(\S+)\s+=>\s+(not found|\S+)")
_SYSTEM_LIB_DIRS = (Path("/usr/lib64"), Path("/lib64"), Path("/usr/lib"))


def load_host_patterns(path: Path) -> list[re.Pattern[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [re.compile(line.strip()) for line in lines if line.strip() and not line.lstrip().startswith("#")]


def is_host(name: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(name) for pattern in patterns)


def is_elf(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(len(_ELF_MAGIC)) == _ELF_MAGIC


def elf_files(bundle: Path) -> list[Path]:
    return sorted(path for path in bundle.rglob("*") if is_elf(path))


def prune_host_libs(bundle: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    removed = []
    for path in sorted(bundle.rglob("*.so*")):
        if (path.is_file() or path.is_symlink()) and is_host(path.name, patterns):
            path.unlink()
            removed.append(str(path.relative_to(bundle)))
    return removed


def parse_ldd(output: str) -> list[tuple[str, str | None]]:
    """[(soname, percorso o None se non trovata)]; vdso e loader non hanno '=>'."""
    deps = []
    for line in output.splitlines():
        match = _LDD_LINE.match(line)
        if match:
            name, target = match.groups()
            deps.append((name, None if target == "not found" else target))
    return deps


def ldd(path: Path, internal: Path) -> list[tuple[str, str | None]]:
    # stesso percorso di ricerca del bootloader di PyInstaller: _internal/ prima
    env = {**os.environ, "LD_LIBRARY_PATH": str(internal)}
    proc = subprocess.run(["ldd", str(path)], capture_output=True, text=True, env=env, check=False)
    # "not a dynamic executable" (binari statici, es. FFmpeg): nessuna dipendenza
    return parse_ldd(proc.stdout) if proc.returncode == 0 else []


def classify(
    bundle: Path, patterns: list[re.Pattern[str]]
) -> tuple[dict[str, Path], dict[str, set[str]]]:
    """(da copiare: soname -> percorso di sistema, mancanti: soname -> chi le chiede)."""
    internal = bundle / "_internal"
    files = elf_files(bundle)
    bundled = {path.name for path in bundle.rglob("*.so*")}
    to_copy: dict[str, Path] = {}
    missing: dict[str, set[str]] = defaultdict(set)
    root = bundle.resolve()
    for path in files:
        for name, target in ldd(path, internal):
            if is_host(name, patterns):
                continue
            if target is None:
                missing[name].add(str(path.relative_to(bundle)))
            elif root not in Path(target).resolve().parents and name not in bundled:
                to_copy[name] = Path(target)
    return to_copy, dict(missing)


def add_system_libs(bundle: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    internal = bundle / "_internal"
    added: list[str] = []
    for _ in range(_MAX_ROUNDS):
        to_copy, missing = classify(bundle, patterns)
        if missing:
            detail = "\n".join(f"  {name}  (richiesta da {', '.join(sorted(owners)[:3])})" for name, owners in sorted(missing.items()))
            raise SystemExit(
                "bundle_libs: dipendenze introvabili e non dell'host (installarle nel "
                f"container di build o aggiungerle a host_libs.txt motivando):\n{detail}"
            )
        if not to_copy:
            return added
        for name, source in sorted(to_copy.items()):
            target = internal / name
            shutil.copy2(source.resolve(), target)
            target.chmod(0o755)
            added.append(name)
    raise SystemExit(f"bundle_libs: nessun punto fisso dopo {_MAX_ROUNDS} giri")


def rpm_origin(name: str) -> str:
    """Pacchetto e licenza della copia di sistema, se c'e' rpm (manylinux)."""
    if shutil.which("rpm") is None:
        return "?"
    for directory in _SYSTEM_LIB_DIRS:
        candidate = directory / name
        if candidate.exists():
            proc = subprocess.run(
                ["rpm", "-qf", "--qf", "%{NAME}-%{VERSION} [%{LICENSE}]", str(candidate)],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
    return "fuori da rpm (da una wheel o dall'interprete)"


def system_libs_report(bundle: Path, added: list[str], removed: list[str]) -> str:
    """Le librerie in _internal/ (non dentro una wheel), con origine e licenza."""
    lines = ["# librerie di sistema nel pacchetto (per THIRD_PARTY_NOTICES)"]
    for path in sorted((bundle / "_internal").glob("*.so*")):
        mark = "aggiunta" if path.name in added else "PyInstaller"
        lines.append(f"{path.name}\t{mark}\t{rpm_origin(path.name)}")
    lines.append("# tolte perche' dell'host (host_libs.txt)")
    lines.extend(removed)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--report"):
        print(__doc__, file=sys.stderr)
        return 2
    bundle, patterns = Path(argv[0]), load_host_patterns(Path(argv[1]))
    if not (bundle / "_internal").is_dir():
        raise SystemExit(f"bundle_libs: {bundle} non e' una cartella di PyInstaller")
    removed = prune_host_libs(bundle, patterns)
    added = add_system_libs(bundle, patterns)
    report = system_libs_report(bundle, added, removed)
    print(report, end="")
    if len(argv) == 4:
        Path(argv[3]).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
