"""La pila legacy del job "compat" e' quella del Mac mini (BUILD_SPEC D7).

Il lock legacy-intel non si installa su Linux, quindi il job usa una copia
delle sue versioni (.github/compat/legacy-requirements.txt). Una copia
puo' allontanarsi dall'originale in silenzio: qui la si confronta, riga
per riga, con requirements-macos-x86_64.lock.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPAT = ROOT / ".github" / "compat" / "legacy-requirements.txt"
LOCK = ROOT / "requirements-macos-x86_64.lock"
# le versioni che definiscono la pila legacy (§2.2): non cambiano mai
CORE = {
    "torch": "2.2.2", "torchaudio": "2.2.2", "numpy": "1.26.4",
    "pyside6": "6.4.3", "demucs": "4.0.1",
}
# PyAV esce dal progetto (D9: il suo FFmpeg e' GPLv3): il lock attuale lo
# contiene ancora, il job compat non deve installarlo
NOT_COPIED = {"av"}
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", re.M)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()  # PEP 503


def _pins(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return {_normalize(n): v.split("+")[0] for n, v in _PIN.findall(text)}


def test_core_versions_are_the_legacy_stack():
    compat = _pins(COMPAT)
    for name, version in CORE.items():
        assert compat.get(name) == version, f"{name}: {compat.get(name)} invece di {version}"


def test_compat_copies_every_lock_version():
    compat, lock = _pins(COMPAT), _pins(LOCK)
    assert lock, "lock legacy vuoto o illeggibile"
    differ = {n: (v, compat.get(n)) for n, v in lock.items()
              if n not in NOT_COPIED and compat.get(n) != v}
    assert not differ, f"lock -> compat diversi o mancanti: {differ}"
    assert not NOT_COPIED & set(compat), "PyAV nel job compat (D9)"


def test_torch_comes_as_cpu_build():
    text = COMPAT.read_text(encoding="utf-8")
    assert re.search(r"^torch==2\.2\.2\+cpu$", text, re.M)
    assert re.search(r"^torchaudio==2\.2\.2\+cpu$", text, re.M)
