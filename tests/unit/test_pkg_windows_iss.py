"""Lo script Inno Setup rispetta §9.7 (letto come testo, gira ovunque).

La compilazione vera sta in tests/integration/test_pkg_windows_compile.py
(solo dove c'è ISCC); qui le regole che un errore di battitura romperebbe
senza che nessuno se ne accorga fino all'utente.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from stemforge.worker.planning import SUPPORTED_SUFFIXES

ROOT = Path(__file__).resolve().parents[2]
ISS = ROOT / "packaging" / "windows" / "stemforge.iss"
INTEGRATION = ROOT / "packaging" / "windows" / "windows_integration.py"


def _section(name: str) -> list[str]:
    text = ISS.read_text(encoding="utf-8-sig")
    match = re.search(rf"^\[{name}\]\n(.*?)(?=^\[\w+\]$|\Z)", text, re.S | re.M)
    assert match, f"sezione [{name}] assente"
    return [line for line in match.group(1).splitlines() if line.strip() and not line.startswith(";")]


def _setup() -> dict[str, str]:
    return dict(line.split("=", 1) for line in _section("Setup"))


def _registry() -> list[dict[str, str]]:
    entries = []
    for line in _section("Registry"):
        fields = dict(re.findall(r'(\w+): ("(?:[^"]|"")*"|[^;]+)', line))
        entries.append({k: _unquote(v.strip()) for k, v in fields.items()})
    return entries


def _unquote(value: str) -> str:
    return value[1:-1].replace('""', '"') if value.startswith('"') else value


def _verifier_constants() -> dict[str, object]:
    """Costanti del verificatore lette senza importarlo: usa winreg, che esiste solo su Windows."""
    tree = ast.parse(INTEGRATION.read_text(encoding="utf-8"))
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, (ast.Constant, ast.Tuple))
    }


def _defines() -> dict[str, str]:
    text = ISS.read_text(encoding="utf-8-sig")
    return dict(re.findall(r'^\s*#define (\w+) "([^"]*)"', text, re.M))


def test_per_user_install_without_admin():
    setup = _setup()
    assert setup["PrivilegesRequired"] == "lowest"
    assert "dialog" in setup["PrivilegesRequiredOverridesAllowed"]
    assert "commandline" in setup["PrivilegesRequiredOverridesAllowed"]  # /CURRENTUSER in CI
    assert setup["DefaultDirName"].startswith("{autopf}")


def test_identity_matches_the_verifier():
    verifier = _verifier_constants()
    assert _setup()["AppId"] == "{" + str(verifier["APP_ID"])
    assert _defines()["ProgId"] == verifier["PROG_ID"]
    assert _defines()["AppExe"] == verifier["APP_EXE"]


def test_open_with_covers_every_format_the_app_reads():
    registry = _registry()
    supported = {e["ValueName"] for e in registry if e["Subkey"].endswith(r"\SupportedTypes")}
    open_with = {
        e["Subkey"].split("\\")[2]
        for e in registry
        if e["Subkey"].endswith(r"\OpenWithProgids") and e["ValueName"] == "{#ProgId}"
    }
    assert supported == set(SUPPORTED_SUFFIXES) == set(_verifier_constants()["EXTENSIONS"])
    assert open_with == set(SUPPORTED_SUFFIXES)


def test_never_steals_the_default_association():
    for entry in _registry():
        subkey = entry["Subkey"]
        if re.fullmatch(r"Software\\Classes\\\.\w+.*", subkey):
            # sotto la chiave dell'estensione solo OpenWithProgids, e solo un nostro valore
            assert subkey.endswith(r"\OpenWithProgids"), subkey
            assert entry["ValueName"] == "{#ProgId}" and entry["ValueType"] == "none"
            # la chiave .ext non è nostra: si toglie il valore, e OpenWithProgids solo se vuota
            assert entry["Flags"].split() == ["uninsdeletevalue", "uninsdeletekeyifempty"], entry["Flags"]


def test_registry_is_removed_on_uninstall():
    owned = [e for e in _registry() if e["Subkey"] in (r"Software\Classes\{#ProgId}", r"Software\Classes\Applications\{#AppExe}")]
    roots = {e["Subkey"] for e in owned if "uninsdeletekey" in e.get("Flags", "")}
    assert roots == {r"Software\Classes\{#ProgId}", r"Software\Classes\Applications\{#AppExe}"}
    assert all(e["Root"] == "HKA" for e in _registry()), "HKA: HKCU per utente, HKLM per tutti"


def test_open_command_quotes_path_and_argument():
    commands = [e["ValueData"] for e in _registry() if e["Subkey"].endswith(r"\shell\open\command")]
    assert commands and all(c == '"{app}\\{#AppExe}" "%1"' for c in commands)


def test_desktop_icon_is_optional_and_off_by_default():
    tasks = " ".join(_section("Tasks"))
    assert 'Name: "desktopicon"' in tasks and "Flags: unchecked" in tasks
    desktop = [line for line in _section("Icons") if "{autodesktop}" in line]
    assert desktop and all("Tasks: desktopicon" in line for line in desktop)
    assert any("{autoprograms}" in line for line in _section("Icons"))


def test_uninstall_asks_before_deleting_and_never_in_silent_mode():
    code = "\n".join(_section("Code"))
    assert "{localappdata}\\{#DataDirName}" in code
    assert _defines()["DataDirName"] == "StemForge"  # §9.2: %LOCALAPPDATA%\StemForge
    silent_exit = code.index("UninstallSilent()")
    assert code.index("Exit;", silent_exit) < code.index("DelTree"), "in silenzio si esce prima di DelTree"
    assert "MB_DEFBUTTON2" in code, "il pulsante predefinito deve essere No"
    assert code.index("MsgBox(") < code.index("DelTree")


@pytest.mark.parametrize("language", ["italian", "english"])
def test_messages_exist_in_both_languages(language: str):
    names = {line.split("=", 1)[0] for line in _section("CustomMessages")}
    for message in ("DeleteUserData", "DeleteFailed", "AudioFileType"):
        assert f"{language}.{message}" in names
