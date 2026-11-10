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


def _package_of(path: Path) -> list[str]:
    """["stemforge", "engine"] per src/stemforge/engine/x.py."""
    return ["stemforge", *path.parent.relative_to(SRC).parts]


def _imports_in(tree: ast.AST, package: list[str]) -> set[str]:
    """Moduli importati, con gli import relativi risolti in assoluto e con
    i nomi presi da un pacchetto: `from .. import engine` dentro ui/ deve
    contare come stemforge.engine, non come un innocuo "stemforge"."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            parts = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join([*parts, *([node.module] if node.module else [])])
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def _imports_of(path: Path) -> set[str]:
    return _imports_in(ast.parse(path.read_text(encoding="utf-8")), _package_of(path))


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
    ui_files = _py_files("ui")
    assert ui_files, "ui/ vuota o spostata: la guardia non controllerebbe niente"
    for path in ui_files:
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


def test_relative_imports_are_resolved():
    """Un `from .. import engine` dentro ui/ non sfugge alle guardie."""
    tree = ast.parse("from .. import engine\nfrom ..export.folder import x\nfrom . import theme")
    names = _imports_in(tree, ["stemforge", "ui"])
    assert {"stemforge.engine", "stemforge.export.folder", "stemforge.ui.theme"} <= names


# -- API di piattaforma (§10.4, D6) -----------------------------------------
# Il motore e' identico ovunque: chi chiede "su che sistema sono?" sta solo
# nei moduli che esistono per rispondere a quella domanda.
PLATFORM_ALLOWED_DIRS = ("ui/",)
PLATFORM_ALLOWED_FILES = ("engine/paths.py", "engine/device.py", "engine/ffmpeg.py")
_PLATFORM_ATTRS = {
    ("sys", "platform"), ("sys", "getwindowsversion"), ("os", "name"),
    ("os", "uname"), ("os", "startfile"),
}
_PLATFORM_MODULES = ("platform", "winreg", "_winreg", "ctypes", "msvcrt", "_winapi")
_FROM_IMPORTS = {("sys", "platform"), ("sys", "getwindowsversion"), ("os", "name"),
                 ("os", "uname"), ("os", "startfile")}
_OPENERS = {"open", "explorer", "explorer.exe", "xdg-open", "gio", "start", "osascript"}
_LAUNCHERS = {"run", "Popen", "call", "check_call", "check_output", "system", "popen"}
# worker/selftest.py descrive il sistema nel report di diagnostica (§9.9,
# §10.5): puo' LEGGERE platform.* per stamparlo, mai decidere in base ad
# esso. Un `if platform.system() == ...` li' resta una violazione, come
# ogni altra API di piattaforma.
REPORT_ONLY = {"worker/selftest.py": frozenset({
    "python_version", "system", "release", "machine", "platform", "mac_ver", "version",
})}


def _dotted(node: ast.AST) -> tuple[str, str] | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id, node.attr
    return None


def _launches_opener(call: ast.Call) -> bool:
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in _LAUNCHERS or not call.args:
        return False
    first = call.args[0]
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        first = first.elts[0]
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return False
    return first.value.split(" ")[0].lower() in _OPENERS


def _decision_nodes(tree: ast.AST) -> set[int]:
    """id dei nodi che stanno dentro un confronto o una condizione."""
    inside: set[int] = set()
    for node in ast.walk(tree):
        tests: list[ast.AST] = []
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            tests.append(node)
        elif isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            tests.append(node.test)
        elif isinstance(node, ast.Match):
            tests.append(node.subject)
        for test in tests:
            inside.update(id(sub) for sub in ast.walk(test))
    return inside


def _report_only_violations(tree: ast.AST, allowed: frozenset[str]) -> list[str]:
    decisions = _decision_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        attr = _dotted(node)
        if attr is None or attr[0] != "platform":
            continue
        if attr[1] not in allowed:
            found.append(f"{node.lineno}: platform.{attr[1]} (non descrittiva)")
        elif id(node) in decisions:
            found.append(f"{node.lineno}: platform.{attr[1]} usata per decidere")
    return found


def _import_uses(node: ast.AST, report_only: bool) -> list[str]:
    if isinstance(node, ast.Import):
        return [f"{node.lineno}: import {a.name}" for a in node.names
                if a.name.split(".")[0] in _PLATFORM_MODULES
                and not (report_only and a.name == "platform")]
    if isinstance(node, ast.ImportFrom) and not node.level and node.module:
        if node.module.split(".")[0] in _PLATFORM_MODULES or any(
            (node.module, a.name) in _FROM_IMPORTS for a in node.names
        ):
            return [f"{node.lineno}: from {node.module} import ..."]
    return []


def platform_api_uses(source: str, report_only: frozenset[str] | None = None) -> list[str]:
    """Usi di API di piattaforma in `source`, come "riga: cosa"."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if (attr := _dotted(node)) in _PLATFORM_ATTRS:
            found.append(f"{node.lineno}: {attr[0]}.{attr[1]}")
        elif isinstance(node, ast.Call) and _launches_opener(node):
            found.append(f"{node.lineno}: lancia un apri-file di sistema")
        else:
            found += _import_uses(node, report_only is not None)
    if report_only is not None:
        found += _report_only_violations(tree, report_only)
    return found


def test_platform_apis_only_where_allowed():
    offenders: list[str] = []
    for path in _py_files():
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith(PLATFORM_ALLOWED_DIRS) or rel in PLATFORM_ALLOWED_FILES:
            continue
        uses = platform_api_uses(path.read_text(encoding="utf-8"), REPORT_ONLY.get(rel))
        offenders += [f"{rel}:{use}" for use in uses]
    assert not offenders, (
        "API di piattaforma fuori da ui/, engine/paths.py, engine/device.py, "
        f"engine/ffmpeg.py (§10.4): {offenders}"
    )


def test_platform_guard_catches_what_it_promises():
    """La guardia deve poter fallire: ogni forma vietata viene vista."""
    caught = [
        "import sys\nif sys.platform == 'darwin': pass",
        "import os\nx = os.name",
        "import platform\nplatform.system()",
        "import winreg",
        "import ctypes.wintypes",
        "from ctypes import windll",
        "from sys import platform",
        "import subprocess\nsubprocess.Popen(['xdg-open', 'x'])",
        "import subprocess\nsubprocess.run(('open', '-R', 'x'))",
        "import os\nos.system('explorer /select,x')",
        "import os\nos.startfile('x')",
    ]
    for snippet in caught:
        assert platform_api_uses(snippet), f"non vista: {snippet!r}"
    allowed = [
        "import sys\nsys.executable\nsys.frozen = True",
        "import os\nos.environ.get('X')\nos.path.join('a', 'b')",
        "import subprocess\nsubprocess.run(['ffmpeg', '-i', 'x'])",
        "with open('x') as f: pass",
    ]
    for snippet in allowed:
        assert not platform_api_uses(snippet), f"falso allarme: {snippet!r}"


def test_report_only_exception_stays_narrow():
    report = REPORT_ONLY["worker/selftest.py"]
    assert not platform_api_uses("import platform\nx = f'{platform.system()}'", report)
    for snippet in (
        "import platform\nif platform.system() == 'Darwin': pass",
        "import platform\nok = platform.machine() in ('arm64',)",
        "import platform\nplatform.win32_ver()",
        "import sys\nsys.platform",
        "import winreg",
    ):
        assert platform_api_uses(snippet, report), f"non vista: {snippet!r}"
