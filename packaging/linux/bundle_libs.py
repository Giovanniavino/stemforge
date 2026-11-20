"""Chiude il pacchetto PyInstaller sulle librerie di sistema (BUILD_SPEC §9.8).

    python bundle_libs.py BUNDLE HOST_LIBS [--report FILE]

BUNDLE e' la cartella di PyInstaller (StemForge + _internal/), HOST_LIBS
l'elenco delle librerie che fornisce il sistema (host_libs.txt).

PyInstaller copia le dipendenze che trova, ma non sa quali sono "del
sistema" su un'altra distribuzione: ne prende alcune che devono restare
dell'host e non segnala quelle che mancano nella build. Qui, in quattro
passi:
1. toglie dal pacchetto cio' che deve venire dall'host, e cio' che
   PyInstaller ha portato solo perche' lo chiedeva una di quelle;
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

import filecmp
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
_SONAME_LINE = re.compile(r"\(SONAME\)\s+Library soname: \[([^\]]+)\]")
# le carica l'interprete o il bootloader, non un DT_NEEDED: mai orfane
_PYTHON_OWNED = re.compile(r"(\.cpython-\d+.*\.so|\.abi3\.so.*|^libpython\d.*\.so.*)$")
# GPL senza eccezioni: nel pacchetto MIT non possono entrare (§11.11).
# libreadline la portava il modulo readline di CPython (build_python.sh)
_GPL_ONLY = re.compile(r"^lib(readline|history)\.so")
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
    soname: str | None = None
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
    soname = _SONAME_LINE.search(output)
    info = ElfInfo(needed=_NEEDED_LINE.findall(output), soname=soname.group(1) if soname else None)
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


def find_orphans(infos: dict[Path, ElfInfo], candidates: set[Path]) -> set[Path]:
    """Candidati che nessun altro file chiede piu', fino al punto fisso.

    Un candidato si riconosce col nome del file o col suo SONAME; l'orfano
    non conta come richiedente, cosi' cadono anche le catene (libgnutls
    chiesta solo da libgio, che e' dell'host).
    """
    orphans: set[Path] = set()
    while True:
        wanted = {name for path, info in infos.items() if path not in orphans for name in info.needed}
        new = {
            path for path in candidates - orphans
            if path.name not in wanted and infos[path].soname not in wanted
        }
        if not new:
            return orphans
        orphans |= new


def prune_orphans(bundle: Path) -> list[str]:
    """Toglie le librerie di sistema che PyInstaller ha preso per una dell'host.

    PyInstaller segue ldd in modo transitivo: per libQt6Core porta glib, e
    per glib libpcre, libmount, libselinux... Tolta glib (host_libs.txt),
    quelle restano nella radice di _internal/, in testa a LD_LIBRARY_PATH,
    e la glib dell'host si ritroverebbe le copie vecchie di AlmaLinux 8 al
    posto delle sue (stesso motivo per cui add_system_libs non le segue).
    """
    internal = bundle / "_internal"
    infos = {path: readelf(path) for path in elf_files(bundle)}
    candidates = {
        path for path in infos
        if path.parent == internal and not _PYTHON_OWNED.search(path.name)
    }
    orphans = find_orphans(infos, candidates)
    for path in orphans:
        path.unlink()
    return sorted(str(path.relative_to(bundle)) for path in [*orphans, *_leftovers(internal)])


def _leftovers(internal: Path) -> list[Path]:
    """Cio' che resta appeso a una libreria tolta: i symlink di PyInstaller
    e le firme FIPS ".libX.so.N.hmac" che gnutls e libgcrypt si portano."""
    stale = [
        path for path in internal.iterdir()
        if (path.is_symlink() and not path.exists())
        or (path.name.startswith(".") and path.name.endswith(".hmac")
            and not (internal / path.name[1:-len(".hmac")]).exists())
    ]
    for path in stale:
        path.unlink()
    return stale


def gpl_only(bundle: Path) -> list[str]:
    return sorted(name for name in bundled_sonames(bundle) if _GPL_ONLY.search(name))


@dataclass
class Scan:
    to_copy: dict[str, Path] = field(default_factory=dict)
    missing: dict[str, set[str]] = field(default_factory=dict)
    too_new: dict[str, list[str]] = field(default_factory=dict)


def bundled_sonames(bundle: Path) -> set[str]:
    """Nomi delle librerie gia' nel pacchetto, in qualsiasi sottocartella."""
    return {path.name for path in bundle.rglob("*.so*") if path.is_file() or path.is_symlink()}


def scan(bundle: Path, files: list[Path], patterns: list[re.Pattern[str]], in_bundle: set[str]) -> Scan:
    """Dipendenze dirette dei file dati: da copiare, introvabili, troppo nuove.

    Una dipendenza con il nome di una libreria gia' nel pacchetto e' sua
    anche se ldd non la trova: torchaudio chiede libtorch.so e libc10.so
    senza RUNPATH, perche' le carica `import torch` (da torch/lib/) prima
    di lui, e il loader riconosce le librerie gia' caricate dal soname.
    """
    internal, root = bundle / "_internal", bundle.resolve()
    result = Scan()
    for path in files:
        info, label = readelf(path), str(path.relative_to(bundle))
        if problems := too_new(info):
            result.too_new[label] = problems
        wanted = [name for name in info.needed if not is_host(name, patterns) and name not in in_bundle]
        resolved = ldd(path, internal) if wanted else {}
        for name in wanted:
            target = resolved.get(name)
            if target is None:
                result.missing.setdefault(name, set()).add(label)
            elif root not in Path(target).resolve().parents:
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
        result = scan(bundle, pending, patterns, bundled_sonames(bundle))
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


def rpm_origin(path: Path) -> str:
    """Pacchetto e licenza della copia di sistema, se e' proprio quella.

    Lo stesso nome non basta: l'immagine ha una libpython3.12 di AlmaLinux
    accanto alla nostra (build_python.sh), e il report la dava per sua.
    """
    if shutil.which("rpm") is None:
        return "?"
    for directory in _SYSTEM_LIB_DIRS:
        candidate = directory / path.name
        if candidate.exists() and filecmp.cmp(candidate, path.resolve(), shallow=False):
            proc = subprocess.run(
                ["rpm", "-qf", "--qf", "%{NAME}-%{VERSION} [%{LICENSE}]", str(candidate)],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
    return "da una wheel o dall'interprete (vedi la licenza del pacchetto Python)"


def system_libs_report(bundle: Path, added: list[str], removed: list[str], orphans: list[str]) -> str:
    """Le librerie in _internal/ (non dentro una wheel), con origine e licenza."""
    lines = ["# librerie nella radice di _internal/ (per THIRD_PARTY_NOTICES)"]
    for path in sorted((bundle / "_internal").glob("[!.]*.so*")):
        mark = "aggiunta" if path.name in added else "PyInstaller"
        lines.append(f"{path.name}\t{mark}\t{rpm_origin(path)}")
    lines.append("# tolte perche' dell'host (host_libs.txt)")
    lines.extend(removed)
    lines.append("# tolte perche' le chiedeva solo una libreria dell'host")
    lines.extend(orphans)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--report"):
        print(__doc__, file=sys.stderr)
        return 2
    bundle, patterns = Path(argv[0]), load_host_patterns(Path(argv[1]))
    if not (bundle / "_internal").is_dir():
        raise SystemExit(f"bundle_libs: {bundle} non e' una cartella di PyInstaller")
    removed = prune_host_libs(bundle, patterns)
    orphans = prune_orphans(bundle)
    added = add_system_libs(bundle, patterns)
    if forbidden := gpl_only(bundle):
        raise SystemExit(f"bundle_libs: librerie solo GPL nel pacchetto MIT: {', '.join(forbidden)}")
    report = system_libs_report(bundle, added, removed, orphans)
    print(report, end="")
    if len(argv) == 4:
        Path(argv[3]).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
