"""Genera e verifica i lock delle tre piattaforme (BUILD_SPEC §2, §9).

Uso:  python packaging/gen_locks.py            # rigenera i lock + verifica
      python packaging/gen_locks.py --check    # verifica soltanto

Per ogni target uv risolve pyproject.toml PER QUELLA piattaforma (anche da
un'altra macchina) e scrive un lock con gli hash SHA-256. Poi ogni pin
viene controllato su PyPI: deve esistere un wheel installabile sul target
— giusta versione di Python, giusta architettura, versione minima di
macOS non oltre quella dichiarata. Se manca, il lock NON è valido: su
quella macchina partirebbe una compilazione da sorgente, cioè il guasto
di sphn/demucs 4.1 visto sul campo (Rust + CMake su un Mac del 2012).

Il lock Intel è quello in uso da mesi sul campo: si rigenera VINCOLATO
alle versioni che contiene già, così cambia solo ciò che si aggiunge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Python puro pubblicato solo come sdist: si installa senza compilatore.
# Tenere allineato con --no-binary nei workflow e negli installer.
SDIST_ALLOWLIST = {"antlr4-python3-runtime", "demucs", "dora-search"}


@dataclass(frozen=True)
class Target:
    name: str
    lock: str
    uv_platform: str
    python: str
    macos_min: tuple[int, int] | None  # None = non macOS
    arch_tags: tuple[str, ...]  # tag di piattaforma accettati nei wheel
    frozen_versions: bool = False  # vincola alle versioni del lock esistente


TARGETS = (
    Target("windows-x64", "requirements-windows-x64.lock", "x86_64-pc-windows-msvc",
           "3.12", None, ("win_amd64",)),
    Target("macos-arm64", "requirements-macos-arm64.lock", "aarch64-apple-darwin",
           "3.12", (11, 0), ("arm64", "universal2")),
    Target("macos-x86_64", "requirements-macos-x86_64.lock", "x86_64-apple-darwin",
           "3.11", (10, 15), ("x86_64", "universal2", "intel"), frozen_versions=True),
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(lock_text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in lock_text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line)
        if match:
            pins[_normalize(match.group(1))] = match.group(2)
    return pins


def _compile(target: Target) -> None:
    lock = ROOT / target.lock
    env = dict(os.environ)
    if target.macos_min is not None:
        env["MACOSX_DEPLOYMENT_TARGET"] = f"{target.macos_min[0]}.{target.macos_min[1]}"
    command = [
        sys.executable, "-m", "uv", "pip", "compile", str(ROOT / "pyproject.toml"),
        "--extra", "ui", "--generate-hashes", "--no-annotate",
        "--python-platform", target.uv_platform, "--python-version", target.python,
        "--output-file", str(lock), "--quiet",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        if target.frozen_versions and lock.exists():
            constraints = Path(tmp) / "constraints.txt"
            constraints.write_text(
                "\n".join(f"{n}=={v}" for n, v in _pins(lock.read_text(encoding="utf-8")).items()),
                encoding="utf-8",
            )
            command += ["--constraint", str(constraints)]
        subprocess.run(command, check=True, env=env, cwd=ROOT)
    print(f"[{target.name}] lock scritto: {target.lock}")


def _pypi_files(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return [entry["filename"] for entry in json.load(response)["urls"]]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    return []


def _python_ok(tags: str, target: Target) -> bool:
    wanted = int(target.python.replace(".", ""))
    if "py3-none" in tags or "py2.py3-none" in tags:
        return True
    match = re.search(r"cp(\d+)-(cp\d+|abi3|none)", tags)
    if not match:
        return False
    built_for = int(match.group(1))
    return built_for == wanted or (match.group(2) == "abi3" and built_for <= wanted)


def _platform_ok(filename: str, target: Target) -> bool:
    if filename.endswith("-any.whl"):
        return True
    if target.macos_min is None:
        return any(tag in filename for tag in target.arch_tags)
    for major, minor, arch in re.findall(r"macosx_(\d+)_(\d+)_(\w+?)(?:\.|\.whl|$)", filename):
        if arch in target.arch_tags and (int(major), int(minor)) <= target.macos_min:
            return True
    return False


def _wheel_ok(filename: str, target: Target) -> bool:
    if not filename.endswith(".whl"):
        return False
    return _python_ok(filename, target) and _platform_ok(filename, target)


def check(target: Target) -> list[str]:
    """Pacchetti del lock che su questo target finirebbero compilati."""
    problems: list[str] = []
    pins = _pins((ROOT / target.lock).read_text(encoding="utf-8"))
    for name, version in sorted(pins.items()):
        files = _pypi_files(name, version)
        if any(_wheel_ok(f, target) for f in files):
            continue
        if name in SDIST_ALLOWLIST and any(f.endswith((".tar.gz", ".zip")) for f in files):
            continue
        problems.append(f"{name}=={version}")
    return problems


def main() -> int:
    only_check = "--check" in sys.argv
    failed = False
    for target in TARGETS:
        if not only_check:
            _compile(target)
        problems = check(target)
        if problems:
            failed = True
            print(f"[{target.name}] SENZA wheel installabile: {', '.join(problems)}", file=sys.stderr)
        else:
            print(f"[{target.name}] ok: ogni pacchetto ha un wheel per il target")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
