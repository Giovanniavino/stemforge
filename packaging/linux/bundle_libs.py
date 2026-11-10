"""Chiude il pacchetto PyInstaller sulle librerie di sistema (BUILD_SPEC §9.8).

    python bundle_libs.py BUNDLE HOST_LIBS [--report FILE]

BUNDLE e' la cartella di PyInstaller (StemForge + _internal/), HOST_LIBS
l'elenco delle librerie che fornisce il sistema (host_libs.txt).

PyInstaller copia le dipendenze che trova, ma non sa quali sono "del
sistema" su un'altra distribuzione: ne prende alcune che devono restare
dell'host e non segnala quelle che mancano nella build. Qui, in quattro
passi:
1. toglie dal pacchetto cio' che deve venire dall'host;
2. aggiunge in _internal/ ogni dipendenza DIRETTA (DT_NEEDED) di un file
   del pacchetto che si risolve fuori dal pacchetto e non e' dell'host,
   poi ripete sulle aggiunte. Le dipendenze delle librerie dell'host non
   si seguono: sono affare dell'host, e una loro copia vecchia nel
   pacchetto verrebbe caricata al posto di quella giusta (il bootloader
   mette _internal/ in testa a LD_LIBRARY_PATH);
3. fallisce se una dipendenza diretta non si trova e non e' dell'host:
   sulla macchina dell'utente Qt direbbe solo "could not load plugin";
4. fallisce se un file chiede simboli di glibc/libstdc++ piu' recenti
   del minimo promesso (§2.1): e' l'equivalente Linux del controllo del
   macOS minimo (§9.1), e protegge Fedora 29 (GCC 8) quanto Ubuntu 20.04.
Le librerie nel pacchetto finiscono nel report con il pacchetto rpm e la
licenza: servono a THIRD_PARTY_NOTICES (§11.11).

Si lancia nel container di build: `ldd` esegue il loader sui file, che
qui sono i nostri; `readelf` viene da binutils.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ELF_MAGIC = b"\x7fELF"
_MAX_ROUNDS = 10  # ogni giro aggiunge le dipendenze delle aggiunte: 3 bastano
_LDD_LINE = re.compile(r"^\s*(\S+)\s+=>\s+(not found|\S+)")
_NEEDED_LINE = re.compile(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]")
_VERSION_REF = re.compile(r"Name: (GLIBC|GLIBCXX|CXXABI)_(\d+(?:\.\d+)*)\b")
_SYSTEM_LIB_DIRS = (Path("/usr/lib64"), Path("/lib64"), Path("/usr/lib"))
# Il minimo promesso: glibc 2.28 (§2.1) e il libstdc++ di GCC 8 (Fedora 29,
# RHEL 8), gli stessi tetti della politica manylinux_2_28 di auditwheel.
SYMBOL_CEILINGS: dict[str, tuple[int, ...]] = {
    "GLIBC": (2, 28),
    "GLIBCXX": (3, 4, 25),
    "CXXABI": (1, 3, 11),
}


@dataclass
class ElfInfo:
    needed: list[str] = field(default_factory=list)
    versions: dict[str, tuple[int, ...]] = field(default_factory=dict)


def load_host_patterns(path: Path) -> list[re.Pattern[str]]:
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [re.compile(line) for line in lines if line and not line.startswith("#")]


def is_host(name: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(name) for pattern in patterns)


def is_elf(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(len(_ELF_MAGIC)) == _ELF_MAGIC


def elf_files(bundle: Path) -> list[Path]:
    return sorted(path for path in bundle.rglob("*") if is_elf(path))


def parse_ldd(output: str) -> dict[str, str | None]:
    """soname -> percorso (None se non trovata); vdso e loader non hanno '=>'."""
    deps: dict[str, str | None] = {}
    for line in output.splitlines():
        match = _LDD_LINE.match(line)
        if match:
            name, target = match.groups()
            deps[name] = None if target == "not found" else target
    return deps


def parse_readelf(output: str) -> ElfInfo:
    """Output di `readelf -d -V -W`: dipendenze dirette e versioni massime chieste."""
    info = ElfInfo(needed=_NEEDED_LINE.findall(output))
    # solo le versioni CHIESTE (.gnu.version_r), non quelle che il file
    # definisce (.gnu.version_d): le intestazioni di sezione stanno a colonna 0
    _, _, needs = output.partition("Version needs section")
    for family, text in _VERSION_REF.findall(needs.split("\nVersion ", 1)[0]):
        version = tuple(int(part) for part in text.split("."))
        info.versions[family] = max(version, info.versions.get(family, version))
    return info


def too_new(info: ElfInfo) -> list[str]:
    return [
        f"{family}_{'.'.join(map(str, version))} > {'.'.join(map(str, SYMBOL_CEILINGS[family]))}"
        for family, version in sorted(info.versions.items())
        if version > SYMBOL_CEILINGS[family]
    ]


def readelf(path: Path) -> ElfInfo:
    proc = subprocess.run(["readelf", "-d", "-V", "-W", str(path)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"bundle_libs: readelf fallito su {path}:\n{proc.stderr}")
    return parse_readelf(proc.stdout)


def ldd(path: Path, internal: Path) -> dict[str, str | None]:
    # stesso percorso di ricerca del bootloader di PyInstaller: _internal/ prima
    env = {**os.environ, "LD_LIBRARY_PATH": str(internal)}
    proc = subprocess.run(["ldd", str(path)], capture_output=True, text=True, env=env, check=False)
    return parse_ldd(proc.stdout) if proc.returncode == 0 else {}


def prune_host_libs(bundle: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    removed = []
    for path in sorted(bundle.rglob("*.so*")):
        if (path.is_file() or path.is_symlink()) and is_host(path.name, patterns):
            path.unlink()
            removed.append(str(path.relative_to(bundle)))
    return removed


@dataclass
class Scan:
    to_copy: dict[str, Path] = field(default_factory=dict)
    missing: dict[str, set[str]] = field(default_factory=dict)
    too_new: dict[str, list[str]] = field(default_factory=dict)


def scan(bundle: Path, files: list[Path], patterns: list[re.Pattern[str]]) -> Scan:
    """Dipendenze dirette dei file dati: da copiare, introvabili, troppo nuove."""
    internal, root = bundle / "_internal", bundle.resolve()
    result = Scan()
    for path in files:
        info, label = readelf(path), str(path.relative_to(bundle))
        if problems := too_new(info):
            result.too_new[label] = problems
        wanted = [name for name in info.needed if not is_host(name, patterns)]
        resolved = ldd(path, internal) if wanted else {}
        for name in wanted:
            target = resolved.get(name)
            if target is None:
                result.missing.setdefault(name, set()).add(label)
            elif root not in Path(target).resolve().parents and not (internal / name).exists():
                result.to_copy[name] = Path(target)
    return result


def _fail_on(result: Scan) -> None:
    if result.missing:
        detail = "\n".join(
            f"  {name}  (chiesta da {', '.join(sorted(owners)[:3])})"
            for name, owners in sorted(result.missing.items())
        )
        raise SystemExit(
            "bundle_libs: dipendenze introvabili e non dell'host (installarle nel "
            f"container di build o aggiungerle a host_libs.txt motivando):\n{detail}"
        )
    if result.too_new:
        detail = "\n".join(f"  {name}: {', '.join(found)}" for name, found in sorted(result.too_new.items()))
        raise SystemExit(f"bundle_libs: simboli oltre il minimo promesso (§2.1):\n{detail}")


def add_system_libs(bundle: Path, patterns: list[re.Pattern[str]]) -> list[str]:
    internal = bundle / "_internal"
    added: list[str] = []
    pending = elf_files(bundle)
    for _ in range(_MAX_ROUNDS):
        result = scan(bundle, pending, patterns)
        _fail_on(result)
        if not result.to_copy:
            return added
        pending = []
        for name, source in sorted(result.to_copy.items()):
            target = internal / name
            shutil.copy2(source.resolve(), target)
            target.chmod(0o755)
            added.append(name)
            pending.append(target)
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
    return "da una wheel o dall'interprete (vedi la licenza del pacchetto Python)"


def system_libs_report(bundle: Path, added: list[str], removed: list[str]) -> str:
    """Le librerie in _internal/ (non dentro una wheel), con origine e licenza."""
    lines = ["# librerie nella radice di _internal/ (per THIRD_PARTY_NOTICES)"]
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
