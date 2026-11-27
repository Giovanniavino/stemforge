"""Famiglie di test (BUILD_SPEC §10.6): marker, giro normale e Makefile.

Il giro normale esclude cio' che pesa; ogni famiglia ha il suo comando
nel Makefile. Qui si controlla che le tre cose restino allineate e che
l'espressione di addopts faccia davvero cio' che promette, valutata dal
motore di espressioni di pytest (pytest e' fissato in ogni lock).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKERS = {"slow", "compat", "fuzz", "chaos", "soak", "frozen", "perf"}
# compat resta nel giro normale: costa pochi secondi (un HTDemucs
# minuscolo, niente pesi) e deve girare a ogni push (§10.6)
EXCLUDED_BY_DEFAULT = {"slow", "fuzz", "chaos", "soak", "frozen", "perf"}
PROFILES = ("legacy-intel", "mac-arm64", "win-x64", "linux-x64")
_COLLECT_TIMEOUT_S = 120


def _ini() -> dict:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]


def _makefile_targets() -> dict[str, str]:
    """target -> ricetta (le righe con il tab che lo seguono)."""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets: dict[str, str] = {}
    current: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.% -]+):(?!=)", line)
        if match and not line.startswith("\t"):
            current = match.group(1).split()
            for name in current:
                targets.setdefault(name, "")
        elif line.startswith("\t"):
            for name in current:
                targets[name] += line.strip() + "\n"
    return targets


def test_markers_are_registered_and_strict():
    ini = _ini()
    registered = {entry.split(":")[0].strip() for entry in ini["markers"]}
    assert registered == MARKERS
    assert "--strict-markers" in ini["addopts"]


def test_default_run_excludes_exactly_the_heavy_families():
    """L'espressione di addopts valutata dal motore di pytest stesso."""
    from _pytest.mark.expression import Expression

    expression = re.search(r"-m '([^']*)'", _ini()["addopts"]).group(1)
    compiled = Expression.compile(expression)
    selected = {m for m in MARKERS if compiled.evaluate(lambda name, **_: name == m)}
    assert selected == MARKERS - EXCLUDED_BY_DEFAULT, expression
    assert compiled.evaluate(lambda name, **_: False), "il test senza marker resta fuori"
    # un test lento E compat (pesi veri) resta fuori dal giro veloce
    assert not compiled.evaluate(lambda name, **_: name in ("slow", "compat"))


def test_makefile_has_a_command_per_family():
    targets = _makefile_targets()
    for marker in MARKERS:
        recipe = targets.get(f"test-{marker}")
        assert recipe is not None, f"Makefile senza test-{marker} (§10.6)"
        assert f"-m {marker}" in recipe, f"test-{marker} non seleziona il marker: {recipe!r}"


def test_makefile_has_the_per_profile_commands():
    targets = _makefile_targets()
    for name in ("dev", "test", "lock", "lock-check", "build", "installer", "selftest",
                 "package", "selftest-package", "ffmpeg"):
        assert name in targets, f"Makefile senza {name}"
    for profile in PROFILES:
        assert f"package-{profile}" in targets
        assert f"selftest-package-{profile}" in targets
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for lock in re.findall(r"^LOCK_[\w-]+\s*:=\s*(\S+)", text, re.M):
        assert lock.startswith("requirements-") and lock.endswith(".lock"), lock


def _run_pytest(tmp_path: Path, test_file: str, *args: str) -> subprocess.CompletedProcess[str]:
    """pytest --collect-only in tmp_path con la sezione VERA di pyproject."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    start = text.index("[tool.pytest.ini_options]")
    end = text.find("\n[", start + 1)
    section = text[start:] if end == -1 else text[start:end]
    ini = tmp_path / "pyproject.toml"
    ini.write_text(section.replace('testpaths = ["tests"]', ""), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "--rootdir", str(tmp_path), "-c", str(ini), str(tmp_path / test_file), *args],
        capture_output=True, text=True, cwd=tmp_path, timeout=_COLLECT_TIMEOUT_S,
    )


def test_command_line_marker_overrides_addopts(tmp_path):
    """Il Makefile e la CI contano su questo: "-m slow" sulla riga di
    comando vince sul -m di addopts (pytest usa l'ultimo). Un solo pytest
    vero, perche' e' un comportamento di pytest e non della nostra
    espressione (quella la valuta il test qui sopra, senza processi)."""
    body = ["import pytest", "", "def test_plain():", "    pass"]
    for marker in sorted(MARKERS):
        body += ["", f"@pytest.mark.{marker}", f"def test_{marker}():", "    pass"]
    (tmp_path / "test_families.py").write_text("\n".join(body) + "\n", encoding="utf-8")
    proc = _run_pytest(tmp_path, "test_families.py", "-m", "slow")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert set(re.findall(r"::test_(\w+)", proc.stdout)) == {"slow"}
