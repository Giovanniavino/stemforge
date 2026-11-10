"""Genera e verifica i lock dei quattro profili (BUILD_SPEC §2.2, D7).

Uso:  python packaging/gen_locks.py            # rigenera i lock + verifica
      python packaging/gen_locks.py --check    # verifica soltanto

Serve `uv` nel Python che lancia lo script (packaging/requirements-build.txt):
uv risolve pyproject.toml PER il profilo, anche da un'altra macchina.

La verifica fallisce se, per un profilo:
- un pacchetto del lock non ha un wheel installabile sul target (giusta
  versione di Python, architettura, macOS minimo o glibc massima): su
  quella macchina partirebbe una compilazione, il guasto di sphn/demucs
  4.1 visto sul campo (Rust + CMake su un Mac del 2012);
- fra gli hash del lock non c'e' quello del file che pip installerebbe:
  `--require-hashes` fallirebbe sulla macchina dell'utente;
- il lock non corrisponde piu' a pyproject.toml (dipendenza aggiunta o
  tolta senza rigenerare): si ririsolve con i pin del lock come vincoli
  e l'insieme dei pacchetti deve restare identico;
- contiene un pacchetto vietato.

Il lock Intel (legacy-intel) e' quello in uso da mesi sul campo: si
rigenera VINCOLATO alle versioni che contiene gia' (D7, "congelato").

Linux: il torch di PyPI per Linux e' la build CUDA, che si tira dietro
~1 GB di librerie nvidia-*. Il profilo e' solo CPU (§2.1), quindi torch e
torchaudio vengono dall'indice CPU di PyTorch (`tool.uv.sources` in
pyproject.toml). uv non scrive nel lock gli indici "explicit": le righe
`--index-url`/`--extra-index-url` le aggiunge questo script, cosi' il lock
si installa con un semplice `pip install -r`. L'indice in piu' non apre a
pacchetti estranei: con `--require-hashes` pip accetta solo i file i cui
hash sono nel lock.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPI_SIMPLE = "https://pypi.org/simple"
PYTORCH_CPU = "https://download.pytorch.org/whl/cpu"
COMPILE_COMMAND = "python packaging/gen_locks.py"
NETWORK_ATTEMPTS = 3
NETWORK_TIMEOUT_S = 60

# Python puro pubblicato solo come sdist: si installa senza compilatore.
# Tenere allineato con --no-binary nei workflow e negli installer.
SDIST_ALLOWLIST = frozenset({"antlr4-python3-runtime", "demucs", "dora-search"})

# Pacchetti che non devono mai rientrare in un lock, con il perche'.
FORBIDDEN = {
    "av": "PyAV include un FFmpeg GPLv3 (BUILD_SPEC D9)",
}

# Tag manylinux storici -> glibc equivalente (PEP 513, 571, 599).
_MANYLINUX_LEGACY = {"manylinux1": (2, 5), "manylinux2010": (2, 12), "manylinux2014": (2, 17)}


@dataclass(frozen=True)
class Target:
    name: str
    lock: str
    uv_platform: str
    python: str
    os_family: str  # "windows" | "macos" | "linux"
    os_version: tuple[int, int] | None  # macOS minimo / glibc massima
    arch_tags: tuple[str, ...]
    frozen_versions: bool = False
    extra_index: str | None = None
    extra_index_packages: frozenset[str] = field(default_factory=frozenset)


TARGETS = (
    Target("windows-x64", "requirements-windows-x64.lock", "x86_64-pc-windows-msvc",
           "3.12", "windows", None, ("amd64",)),
    Target("macos-arm64", "requirements-macos-arm64.lock", "aarch64-apple-darwin",
           "3.12", "macos", (11, 0), ("arm64", "universal2")),
    Target("macos-x86_64", "requirements-macos-x86_64.lock", "x86_64-apple-darwin",
           "3.11", "macos", (10, 15), ("x86_64", "universal2", "intel"), frozen_versions=True),
    Target("linux-x64", "requirements-linux-x64.lock", "x86_64-manylinux_2_28",
           "3.12", "linux", (2, 28), ("x86_64",),
           extra_index=PYTORCH_CPU, extra_index_packages=frozenset({"torch", "torchaudio"})),
)


# ------------------------------------------------------------------ lock

def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(text: str) -> dict[str, tuple[str, frozenset[str]]]:
    """nome normalizzato -> (versione, hash sha256) da un lock con hash."""
    logical = re.sub(r"\\\r?\n", " ", text)
    entries: dict[str, tuple[str, frozenset[str]]] = {}
    for line in logical.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line)
        if match:
            hashes = frozenset(re.findall(r"--hash=sha256:([0-9a-f]{64})", line))
            entries[normalize(match.group(1))] = (match.group(2), hashes)
    return entries


def pins_of(text: str) -> dict[str, str]:
    return {name: version for name, (version, _) in parse_lock(text).items()}


def _with_index_lines(text: str, target: Target) -> str:
    if target.extra_index is None:
        return text
    lines = text.splitlines(keepends=True)
    header = 0
    while header < len(lines) and lines[header].startswith("#"):
        header += 1
    index = [f"--index-url {PYPI_SIMPLE}\n", f"--extra-index-url {target.extra_index}\n"]
    return "".join(lines[:header] + index + lines[header:])


def _uv_command(target: Target, output: Path, constraints: Path | None) -> list[str]:
    command = [
        sys.executable, "-m", "uv", "pip", "compile", str(ROOT / "pyproject.toml"),
        "--extra", "ui", "--generate-hashes", "--no-annotate", "--quiet",
        "--python-platform", target.uv_platform, "--python-version", target.python,
        "--custom-compile-command", COMPILE_COMMAND, "--output-file", str(output),
    ]
    if constraints is not None:
        command += ["--constraint", str(constraints)]
    return command


def compile_lock(target: Target, output: Path, frozen_to: dict[str, str] | None) -> None:
    """Risolve pyproject per il profilo e scrive `output` (con hash)."""
    if importlib.util.find_spec("uv") is None:
        raise SystemExit("uv non installato: python -m pip install -r packaging/requirements-build.txt")
    env = dict(os.environ)
    if target.os_family == "macos" and target.os_version is not None:
        env["MACOSX_DEPLOYMENT_TARGET"] = "{}.{}".format(*target.os_version)
    with tempfile.TemporaryDirectory() as tmp:
        constraints = None
        if frozen_to:
            constraints = Path(tmp) / "constraints.txt"
            constraints.write_text(
                "".join(f"{n}=={v}\n" for n, v in sorted(frozen_to.items())), encoding="utf-8"
            )
        subprocess.run(_uv_command(target, output, constraints), check=True, env=env, cwd=ROOT)
    text = output.read_text(encoding="utf-8")
    output.write_text(_with_index_lines(text, target), encoding="utf-8", newline="\n")


# ------------------------------------------------------------ wheel tags

def wheel_tags(filename: str) -> tuple[set[str], set[str], set[str]] | None:
    """(python, abi, piattaforma) di un nome di wheel, None se non e' un wheel."""
    if not filename.endswith(".whl"):
        return None
    parts = filename[: -len(".whl")].split("-")
    if len(parts) < 5:
        return None
    python, abi, platform = parts[-3:]
    return set(python.split(".")), set(abi.split(".")), set(platform.split("."))


def _python_ok(pythons: set[str], abis: set[str], target: Target) -> bool:
    wanted = int(target.python.replace(".", ""))
    for python in pythons:
        if python in ("py3", f"py{wanted}") and "none" in abis:
            return True
        if not re.fullmatch(r"cp\d+", python):
            continue
        built_for = int(python[2:])
        if built_for == wanted and abis & {f"cp{wanted}", "none", "abi3"}:
            return True
        if built_for <= wanted and "abi3" in abis:
            return True
    return False


def _glibc_of(platform: str, arch: str) -> tuple[int, int] | None:
    for legacy, version in _MANYLINUX_LEGACY.items():
        if platform == f"{legacy}_{arch}":
            return version
    match = re.fullmatch(rf"manylinux_(\d+)_(\d+)_{arch}", platform)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _one_platform_ok(platform: str, target: Target) -> bool:
    if platform == "any":
        return True
    if target.os_family == "windows":
        return any(platform == f"win_{arch}" for arch in target.arch_tags)
    if target.os_family == "linux":
        assert target.os_version is not None
        return any(
            (glibc := _glibc_of(platform, arch)) is not None and glibc <= target.os_version
            for arch in target.arch_tags
        )
    match = re.fullmatch(r"macosx_(\d+)_(\d+)_(\w+)", platform)
    if not match or match.group(3) not in target.arch_tags:
        return False
    assert target.os_version is not None
    return (int(match.group(1)), int(match.group(2))) <= target.os_version


def installable(filename: str, target: Target) -> bool:
    """True se pip installerebbe questo wheel sul profilo senza compilare."""
    tags = wheel_tags(filename)
    if tags is None:
        return False
    pythons, abis, platforms = tags
    return _python_ok(pythons, abis, target) and any(
        _one_platform_ok(p, target) for p in platforms
    )


# --------------------------------------------------------------- indici

def _fetch(url: str, accept: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept})
    for attempt in range(NETWORK_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT_S) as response:
                return response.read()
        except OSError:
            if attempt == NETWORK_ATTEMPTS - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("irraggiungibile")


def files_from_simple_html(html: str, name: str, version: str) -> list[tuple[str, str]]:
    """(nome file, sha256) di una versione da una pagina PEP 503."""
    found: list[tuple[str, str]] = []
    for href, digest in re.findall(r'href="([^"#]+)#sha256=([0-9a-f]{64})"', html):
        filename = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        parts = filename.split("-")
        if len(parts) > 1 and normalize(parts[0]) == name and parts[1] == version:
            found.append((filename, digest))
    return found


class IndexCache:
    """File pubblicati per (pacchetto, versione), letti una volta per run."""

    def __init__(self) -> None:
        self._pages: dict[str, str] = {}
        self._pypi: dict[tuple[str, str], list[tuple[str, str]]] = {}

    def files(self, name: str, version: str, index: str | None) -> list[tuple[str, str]]:
        if index is not None:
            url = f"{index}/{name}/"
            if url not in self._pages:
                self._pages[url] = _fetch(url, "text/html").decode("utf-8")
            return files_from_simple_html(self._pages[url], name, version)
        key = (name, version)
        if key not in self._pypi:
            data = json.loads(_fetch(f"https://pypi.org/pypi/{name}/{version}/json", "application/json"))
            self._pypi[key] = [(f["filename"], f["digests"]["sha256"]) for f in data["urls"]]
        return self._pypi[key]


# ------------------------------------------------------------- verifica

def pin_problem(name: str, hashes: frozenset[str], files: list[tuple[str, str]],
                target: Target) -> str | None:
    """Perche' questo pin non si installa sul profilo, o None se si installa."""
    if not hashes:
        return "nessun hash nel lock"
    wheels = [(f, h) for f, h in files if installable(f, target)]
    if name in SDIST_ALLOWLIST and not wheels:
        wheels = [(f, h) for f, h in files if f.endswith((".tar.gz", ".zip"))]
    if not wheels:
        return "nessun wheel installabile sul target"
    if not any(h in hashes for _, h in wheels):
        return "l'hash del file installabile non e' nel lock"
    return None


def check_installable(target: Target, text: str, cache: IndexCache) -> list[str]:
    problems: list[str] = []
    for name, (version, hashes) in sorted(parse_lock(text).items()):
        if name in FORBIDDEN:
            problems.append(f"{name}: vietato, {FORBIDDEN[name]}")
            continue
        index = target.extra_index if name in target.extra_index_packages else None
        problem = pin_problem(name, hashes, cache.files(name, version, index), target)
        if problem:
            problems.append(f"{name}=={version}: {problem}")
    if target.extra_index and f"--extra-index-url {target.extra_index}" not in text:
        problems.append(f"manca la riga --extra-index-url {target.extra_index}")
    return problems


def diff_pins(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    """Differenze fra i pin risolti da pyproject (expected) e quelli del lock."""
    problems = [f"{n}: manca nel lock" for n in sorted(expected.keys() - actual.keys())]
    problems += [f"{n}: nel lock ma non richiesto da pyproject" for n in sorted(actual.keys() - expected.keys())]
    problems += [
        f"{n}: pyproject risolve {expected[n]}, il lock ha {actual[n]}"
        for n in sorted(expected.keys() & actual.keys())
        if expected[n] != actual[n]
    ]
    return problems


def check_matches_pyproject(target: Target, text: str) -> list[str]:
    current = pins_of(text)
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "lock.txt"
        compile_lock(target, output, frozen_to=current)
        resolved = pins_of(output.read_text(encoding="utf-8"))
    return diff_pins(resolved, current)


def check(target: Target, cache: IndexCache) -> list[str]:
    path = ROOT / target.lock
    if not path.exists():
        return [f"{target.lock} non esiste"]
    text = path.read_text(encoding="utf-8")
    return check_matches_pyproject(target, text) + check_installable(target, text, cache)


def regenerate(target: Target) -> None:
    path = ROOT / target.lock
    frozen_to = None
    if target.frozen_versions and path.exists():
        frozen_to = pins_of(path.read_text(encoding="utf-8"))
    compile_lock(target, path, frozen_to)
    print(f"[{target.name}] lock scritto: {target.lock}")


def main(argv: list[str]) -> int:
    only_check = "--check" in argv
    cache = IndexCache()
    failed = False
    for target in TARGETS:
        if not only_check:
            regenerate(target)
        problems = check(target, cache)
        if problems:
            failed = True
            print(f"[{target.name}] LOCK NON VALIDO:", file=sys.stderr)
            for problem in problems:
                print(f"    {problem}", file=sys.stderr)
        else:
            print(f"[{target.name}] ok: coerente con pyproject, ogni pacchetto ha un wheel e il suo hash")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
