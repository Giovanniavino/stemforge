"""Verifica che OGNI binario dentro StemForge.app giri sul macOS promesso.

    python packaging/macos/check_min_os.py packaging/dist/StemForge.app 10.15 [--arch x86_64]

I runner di CI hanno solo macOS recenti, ma l'app promette 10.15 (Intel)
e 11.0 (Apple Silicon). Ogni file Mach-O dichiara il macOS minimo con cui
è stato compilato (LC_BUILD_VERSION minos, o LC_VERSION_MIN_MACOSX): se
anche una sola libreria del pacchetto chiede di più, su quei Mac l'app
non si apre. Questo controllo lo scopre in CI, senza avere quei Mac.

Con --arch si guarda solo la fetta che quel Mac caricherà davvero: una
libreria universal2 nel pacchetto Intel ha una fetta arm64 che chiede per
forza macOS 11, ed è innocua. Un binario che non dichiara il minimo, o
che otool non riesce a leggere, è un errore: ciò che non si misura non si
può garantire.

La lettura dell'output di otool è separata dall'esecuzione di otool
(parametro run_otool), così il parsing si collauda anche fuori dal Mac.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

OtoolRunner = Callable[[Path], str]
Version = tuple[int, ...]

_THIN_MAGICS = {
    b"\xfe\xed\xfa\xce": ">", b"\xce\xfa\xed\xfe": "<",  # 32 bit
    b"\xfe\xed\xfa\xcf": ">", b"\xcf\xfa\xed\xfe": "<",  # 64 bit
}
_FAT_MAGICS = (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")  # universale, 32 e 64 bit
# CAFEBABE è anche la firma delle classi Java: lì al posto del numero di
# fette c'è la versione del formato (>= 45). Stessa soglia di file(1).
_MAX_FAT_SLICES = 30
_CPU_TYPES = {7: "i386", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64"}
_VERSION_COMMANDS = ("LC_BUILD_VERSION", "LC_VERSION_MIN_MACOSX")
# LC_BUILD_VERSION platform: 1 = macOS (otool classico stampa il numero o
# MACOS, llvm-otool "macos"); le altre piattaforme non riguardano il Mac
_MACOS_PLATFORM_NAMES = ("1", "macos")
UNKNOWN_ARCH = "?"


class OtoolError(RuntimeError):
    """otool non è riuscito a leggere un file che sembrava Mach-O."""


def parse_version(text: str) -> Version:
    """'10.15.0' e '10.15' sono la stessa versione: gli zeri finali non contano."""
    parts = [int(part) for part in text.strip().split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def pretty(version: Version) -> str:
    return ".".join(map(str, version if len(version) > 1 else (*version, 0)))


def macho_arch(head: bytes) -> str | None:
    """Dai primi 8 byte: None se non è Mach-O, "fat" se universale,
    altrimenti l'architettura del binario thin."""
    magic = head[:4]
    if magic in _FAT_MAGICS and len(head) >= 8:
        slices = struct.unpack(">I", head[4:8])[0]
        return "fat" if 0 < slices <= _MAX_FAT_SLICES else None
    if magic in _THIN_MAGICS and len(head) >= 8:
        cputype = struct.unpack(_THIN_MAGICS[magic] + "I", head[4:8])[0]
        return _CPU_TYPES.get(cputype, f"cpu{cputype:#x}")
    return None


def parse_otool(output: str, default_arch: str = UNKNOWN_ARCH) -> dict[str, Version | None]:
    """Output di `otool -arch all -l` -> {architettura: macOS minimo o None}.

    I binari fat hanno un'intestazione "(architecture X)" per fetta; quelli
    thin no, e per loro vale default_arch (letta dall'intestazione Mach-O).
    """
    found: dict[str, list[Version]] = {}
    arch: str | None = None
    command: str | None = None
    is_macos = True
    for line in output.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("):") and "(architecture " in stripped:
            arch = stripped.rsplit("(architecture ", 1)[1][:-2]
            found.setdefault(arch, [])
            command = None
            continue
        tokens = stripped.split()
        if len(tokens) < 2:
            continue
        key, value = tokens[0], tokens[1]
        if key == "cmd":
            command = value if value in _VERSION_COMMANDS else None
            is_macos = True
            if command and arch is None:
                arch = default_arch
                found.setdefault(arch, [])
        elif command == "LC_BUILD_VERSION" and key == "platform":
            is_macos = value.lower() in _MACOS_PLATFORM_NAMES
        elif (command, key) in (("LC_BUILD_VERSION", "minos"), ("LC_VERSION_MIN_MACOSX", "version")):
            if is_macos and arch is not None:
                found[arch].append(parse_version(value))
            command = None
    return {name: max(versions) if versions else None for name, versions in found.items()}


def run_otool(path: Path) -> str:
    result = subprocess.run(
        ["otool", "-arch", "all", "-l", str(path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OtoolError(result.stderr.strip() or f"codice di uscita {result.returncode}")
    return result.stdout


def _read_head(path: Path) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(8)
    except OSError:
        return b""


def _macho_files(app: Path) -> Iterator[tuple[Path, str]]:
    # i link simbolici (Resources <-> Frameworks nei bundle PyInstaller)
    # puntano a file già controllati: si salta il doppione
    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        kind = macho_arch(_read_head(path))
        if kind is not None:
            yield path, kind


def _problems_of(
    name: str, slices: dict[str, Version | None], promised: Version, arch: str | None
) -> list[str]:
    if arch is not None and slices and arch not in slices and UNKNOWN_ARCH not in slices:
        return [f"{name} non contiene la fetta {arch}: su quel Mac non si carica"]
    if not slices:
        return [f"{name} non dichiara il macOS minimo"]
    problems: list[str] = []
    for slice_arch, minimum in slices.items():
        if arch is not None and slice_arch not in (arch, UNKNOWN_ARCH):
            continue
        if minimum is None:
            problems.append(f"{name} [{slice_arch}] non dichiara il macOS minimo")
        elif minimum > promised:
            problems.append(f"{name} [{slice_arch}] richiede macOS {pretty(minimum)}")
    return problems


def check_bundle(
    app: Path, promised: Version, arch: str | None = None, otool: OtoolRunner = run_otool
) -> tuple[int, list[str]]:
    """(binari Mach-O controllati, problemi trovati)."""
    checked = 0
    problems: list[str] = []
    for path, kind in _macho_files(app):
        checked += 1
        name = path.relative_to(app).as_posix()
        try:
            output = otool(path)
        except OtoolError as error:
            problems.append(f"{name}: otool non riesce a leggerlo ({error})")
            continue
        default_arch = UNKNOWN_ARCH if kind == "fat" else kind
        problems.extend(_problems_of(name, parse_otool(output, default_arch), promised, arch))
    return checked, problems


def main(argv: list[str] | None = None, otool: OtoolRunner = run_otool) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", type=Path, help="StemForge.app (o una cartella di binari)")
    parser.add_argument("promised", help="macOS minimo promesso, es. 10.15 o 11.0")
    parser.add_argument("--arch", choices=sorted(set(_CPU_TYPES.values())),
                        help="controlla solo la fetta che quel Mac carica")
    args = parser.parse_args(argv)
    if not args.app.is_dir():
        print(f"non trovato: {args.app}", file=sys.stderr)
        return 2
    try:
        checked, problems = check_bundle(args.app, parse_version(args.promised), args.arch, otool)
    except FileNotFoundError:
        print("otool non trovato: questo controllo gira sul Mac con gli Xcode "
              "Command Line Tools (xcode-select --install)", file=sys.stderr)
        return 2
    if checked == 0:
        print(f"nessun binario Mach-O in {args.app}: percorso sbagliato?", file=sys.stderr)
        return 1
    if problems:
        print(f"{len(problems)} problemi rispetto a macOS {args.promised}:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    scope = f", fetta {args.arch}" if args.arch else ""
    print(f"ok: {checked} binari Mach-O{scope}, nessuno richiede più di macOS {args.promised}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
