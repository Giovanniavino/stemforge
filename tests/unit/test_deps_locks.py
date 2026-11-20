"""packaging/gen_locks.py e i quattro lock (BUILD_SPEC §2.2, D7, D9).

Senza rete: la logica dei tag dei wheel e i lock come stanno nel repo.
La verifica contro PyPI vera e' "python packaging/gen_locks.py --check".
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ("requirements-windows-x64.lock", "requirements-macos-arm64.lock",
         "requirements-macos-x86_64.lock", "requirements-linux-x64.lock")

# legacy-intel e' congelato (D7): questi pin sono quelli provati sul campo
# (lock di 9bde2d4 meno 12 pacchetti finiti li' per errore). Cambiarne uno
# richiede una decisione esplicita, non una rigenerazione.
LEGACY_FROZEN = {
    "antlr4-python3-runtime": "4.9.3", "certifi": "2026.7.22", "cffi": "2.1.1",
    "cloudpickle": "3.1.2", "demucs": "4.0.1", "dora-search": "0.1.12", "einops": "0.8.2",
    "filelock": "3.32.2", "fsspec": "2026.7.0", "jinja2": "3.1.6", "julius": "0.2.8",
    "lameenc": "1.8.4", "markupsafe": "3.0.3", "mpmath": "1.3.0", "networkx": "3.6.1",
    "numpy": "1.26.4", "omegaconf": "2.3.1", "openunmix": "1.3.0", "pycparser": "3.0",
    "pyside6": "6.4.3", "pyside6-addons": "6.4.3", "pyside6-essentials": "6.4.3",
    "pyyaml": "6.0.3", "retrying": "1.4.2", "shiboken6": "6.4.3", "soundfile": "0.14.0",
    "submitit": "1.5.4", "sympy": "1.14.0", "torch": "2.2.2", "torchaudio": "2.2.2",
    "tqdm": "4.70.0", "treetable": "0.2.6", "typing-extensions": "4.16.0",
}


def _load_gen_locks() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_locks", ROOT / "packaging" / "gen_locks.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_locks"] = module  # dataclass vuole il modulo registrato
    spec.loader.exec_module(module)
    return module


gl = _load_gen_locks()
TARGET = {t.name: t for t in gl.TARGETS}


def _lock(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(("filename", "ok"), [
    ("torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl", True),
    ("numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl", True),
    ("a-1-cp312-cp312-manylinux1_x86_64.whl", True),
    ("a-1-cp312-cp312-manylinux2010_x86_64.whl", True),
    ("a-1-cp39-abi3-manylinux2014_x86_64.whl", True),
    ("a-1-py3-none-any.whl", True),
    ("a-1-cp312-cp312-manylinux_2_31_x86_64.whl", False),  # glibc troppo nuova
    ("a-1-cp312-cp312-manylinux_3_0_x86_64.whl", False),
    ("a-1-cp312-cp312-musllinux_1_2_x86_64.whl", False),
    ("a-1-cp312-cp312-manylinux_2_28_aarch64.whl", False),
    ("a-1-cp311-cp311-manylinux_2_28_x86_64.whl", False),  # altro Python
    ("a-1-cp313-abi3-manylinux_2_28_x86_64.whl", False),  # abi3 piu' nuovo
    ("a-1-cp312-cp312-linux_x86_64.whl", False),  # non manylinux
    ("a-1.tar.gz", False),
])
def test_linux_wheel_tags(filename, ok):
    assert gl.installable(filename, TARGET["linux-x64"]) is ok


@pytest.mark.parametrize(("target", "filename", "ok"), [
    ("macos-x86_64", "a-1-cp311-cp311-macosx_10_9_x86_64.whl", True),
    ("macos-x86_64", "a-1-cp311-cp311-macosx_10_15_universal2.whl", True),
    ("macos-x86_64", "a-1-cp311-cp311-macosx_11_0_x86_64.whl", False),  # Catalina no
    ("macos-x86_64", "a-1-cp312-cp312-macosx_10_9_x86_64.whl", False),
    ("macos-x86_64", "a-1-cp311-cp311-macosx_10_9_arm64.whl", False),
    ("macos-arm64", "a-1-cp312-cp312-macosx_11_0_arm64.whl", True),
    ("macos-arm64", "a-1-cp312-cp312-macosx_14_0_arm64.whl", False),  # torch >= 2.12
    ("macos-arm64", "a-1-cp312-cp312-macosx_10_9_x86_64.whl", False),
    ("windows-x64", "a-1-cp312-cp312-win_amd64.whl", True),
    ("windows-x64", "a-1-cp312-cp312-win32.whl", False),
    ("windows-x64", "a-1-cp312-cp312-win_arm64.whl", False),
    ("windows-x64", "a-1-cp312-cp312-manylinux_2_28_x86_64.whl", False),
])
def test_other_profiles_wheel_tags(target, filename, ok):
    assert gl.installable(filename, TARGET[target]) is ok


def test_pin_problem_allows_sdist_only_for_the_allowlist():
    linux = TARGET["linux-x64"]
    sdist = [("demucs-4.0.1.tar.gz", "a" * 64)]
    assert gl.pin_problem("demucs", frozenset({"a" * 64}), sdist, linux) is None
    other = [("lameenc-1.0.tar.gz", "a" * 64)]
    assert gl.pin_problem("lameenc", frozenset({"a" * 64}), other, linux) is not None
    wheel = [("x-1-py3-none-any.whl", "b" * 64)]
    assert "hash" in gl.pin_problem("x", frozenset({"c" * 64}), wheel, linux)
    assert "hash" in gl.pin_problem("x", frozenset(), wheel, linux)


def test_simple_index_page_matches_local_versions_exactly():
    html = (
        '<a href="/whl/cpu/torch-2.10.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl'
        '#sha256=' + "1" * 64 + '" data-dist-info-metadata="sha256=' + "9" * 64 + '">x</a>\n'
        '<a href="/whl/cpu/torch-2.10.0-cp312-none-macosx_11_0_arm64.whl#sha256=' + "2" * 64 + '">y</a>\n'
        '<a href="/whl/cpu/torchaudio-2.10.0%2Bcpu-cp312-cp312-win_amd64.whl#sha256=' + "3" * 64 + '">z</a>\n'
    )
    assert gl.files_from_simple_html(html, "torch", "2.10.0+cpu") == [
        ("torch-2.10.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl", "1" * 64)
    ]
    assert [d for _, d in gl.files_from_simple_html(html, "torch", "2.10.0")] == ["2" * 64]


def test_index_lines_go_after_the_header_and_are_parsed_away():
    body = "# generato\n#    comando\nx==1 \\\n    --hash=sha256:" + "a" * 64 + "\n"
    text = gl._with_index_lines(body, TARGET["linux-x64"])
    lines = text.splitlines()
    assert lines[2] == f"--index-url {gl.PYPI_SIMPLE}"
    assert lines[3] == f"--extra-index-url {gl.PYTORCH_CPU}"
    assert gl.parse_lock(text) == {"x": ("1", frozenset({"a" * 64}))}
    assert gl._with_index_lines(body, TARGET["windows-x64"]) == body


def test_diff_pins_names_every_kind_of_drift():
    problems = gl.diff_pins({"a": "1", "b": "2"}, {"b": "3", "c": "1"})
    assert problems == ["a: manca nel lock", "c: nel lock ma non richiesto da pyproject",
                        "b: pyproject risolve 2, il lock ha 3"]


def test_legacy_lock_is_frozen():
    assert gl.pins_of(_lock("requirements-macos-x86_64.lock")) == LEGACY_FROZEN


@pytest.mark.parametrize("lock", LOCKS)
def test_every_lock_is_hashed_and_free_of_forbidden_packages(lock):
    entries = gl.parse_lock(_lock(lock))
    assert {"torch", "torchaudio", "demucs", "pyside6", "soundfile", "certifi"} <= entries.keys()
    assert not entries.keys() & gl.FORBIDDEN.keys()
    assert all(hashes for _, hashes in entries.values())


def test_linux_lock_is_the_cpu_build_with_its_index():
    text = _lock("requirements-linux-x64.lock")
    pins = gl.pins_of(text)
    assert pins["torch"] == "2.10.0+cpu" and pins["torchaudio"] == "2.10.0+cpu"
    assert f"--extra-index-url {gl.PYTORCH_CPU}" in text.splitlines()
    assert not [n for n in pins if n.startswith(("nvidia-", "triton"))]


def test_pyproject_has_no_pyav_and_an_spdx_license():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names = [d.split(";")[0].split("=")[0].split("<")[0].split(">")[0].strip().lower()
             for d in project["dependencies"]]
    assert "av" not in names and "torch" in names
    assert project["license"] == "MIT" and project["license-files"] == ["LICENSE"]


def test_obsolete_lock_tools_are_gone():
    assert not (ROOT / "packaging" / "gen_macos_lock.py").exists()
    assert not (ROOT / "requirements-dev-win.lock").exists()
