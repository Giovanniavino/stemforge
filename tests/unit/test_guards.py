"""Guardie architetturali: test veri, non convenzioni (BUILD_SPEC §10.4).

Sono i test che impediscono al progetto di tornare quello di prima.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "stemforge"

MAX_FILE_LINES = 400
MAX_FUNCTION_LINES = 50


def _py_files(subdir: str = "") -> list[Path]:
    root = SRC / subdir if subdir else SRC
    return sorted(root.rglob("*.py"))


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_file_over_400_lines():
    offenders = [
        f"{path.relative_to(SRC)}: {count} righe"
        for path in _py_files()
        if (count := len(path.read_text(encoding="utf-8").splitlines())) > MAX_FILE_LINES
    ]
    assert not offenders, f"file oltre {MAX_FILE_LINES} righe: {offenders}"


def test_no_function_over_50_lines():
    offenders: list[str] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length > MAX_FUNCTION_LINES:
                    offenders.append(
                        f"{path.relative_to(SRC)}:{node.lineno} {node.name} ({length})"
                    )
    assert not offenders, f"funzioni oltre {MAX_FUNCTION_LINES} righe: {offenders}"


def test_engine_never_imports_ui():
    for subdir in ("engine", "model", "worker", "export"):
        for path in _py_files(subdir):
            for name in _imports_of(path):
                assert not name.startswith("stemforge.ui"), (
                    f"{path.relative_to(SRC)} importa {name}: "
                    "le dipendenze scorrono in una direzione sola (§3)"
                )


def test_ui_never_imports_engine_or_heavy_libs():
    # I widget parlano solo con bridge.py; niente torch/soundfile/engine (§8.5)
    forbidden_prefixes = ("stemforge.engine", "stemforge.export", "torch", "soundfile", "demucs")
    ui_dir = SRC / "ui"
    if not ui_dir.exists():
        return
    for path in _py_files("ui"):
        for name in _imports_of(path):
            for prefix in forbidden_prefixes:
                assert not (name == prefix or name.startswith(prefix + ".")), (
                    f"ui/{path.name} importa {name}: vietato (§8.5)"
                )


def test_model_layer_has_no_io():
    # model = dati puri: niente torch/numpy/soundfile, niente I/O (§3)
    forbidden = ("torch", "numpy", "soundfile", "os", "io", "shutil", "subprocess")
    for path in _py_files("model"):
        imports = _imports_of(path)
        for name in imports:
            root = name.split(".")[0]
            assert root not in forbidden, f"model/{path.name} importa {name}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "open", f"model/{path.name} chiama open()"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("write_text", "read_text", "write_bytes", "read_bytes"), (
                    f"model/{path.name} fa I/O su Path: {node.func.attr}"
                )


def test_model_layer_imports_only_model():
    for path in _py_files("model"):
        for name in _imports_of(path):
            if name.startswith("stemforge"):
                assert name.startswith("stemforge.model"), (
                    f"model/{path.name} importa {name}: model non importa nulla del progetto (§3)"
                )
