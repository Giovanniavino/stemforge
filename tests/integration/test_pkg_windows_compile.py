"""stemforge.iss compila davvero, [Code] compreso (§9.7).

Gira solo dove c'è Inno Setup (dev-box Windows, runner Windows della CI).
Non serve l'app costruita: al posto di packaging/dist/StemForge c'è un
eseguibile finto, perché qui si collauda lo script, non PyInstaller.
Compila con la stessa funzione che usa la build vera (build_installer.py).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "packaging" / "windows"
_COMPILE_TIMEOUT_S = 120
_FAKE_DEEP_FILE = "_internal/una/cartella/profonda/libreria.dll"

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Inno Setup: solo Windows")


@pytest.fixture()
def tools(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    pytest.importorskip("PIL")
    monkeypatch.syspath_prepend(str(WINDOWS))
    import build_installer
    import windows_integration

    iscc = windows_integration.find_iscc()
    if iscc is None:
        pytest.skip("serve Inno Setup 6 (ISCC.exe)")
    return build_installer, iscc


@pytest.fixture()
def packaging_copy(tmp_path: Path) -> Path:
    """Una copia di packaging/ con un'app finta dove l'installer se l'aspetta."""
    packaging = tmp_path / "repo" / "packaging"
    (packaging / "windows").mkdir(parents=True)
    shutil.copy(WINDOWS / "stemforge.iss", packaging / "windows")
    app = packaging / "dist" / "StemForge"
    (app / _FAKE_DEEP_FILE).parent.mkdir(parents=True)
    (app / "StemForge.exe").write_bytes(b"MZ finto")
    (app / _FAKE_DEEP_FILE).write_bytes(b"dll finta")
    return packaging


def test_installer_script_compiles(tools, packaging_copy: Path):
    build_installer, iscc = tools
    setup = build_installer.compile_installer(iscc, packaging_copy, "1.2.3")
    assert setup == packaging_copy.parent / "dist" / "StemForge-1.2.3-windows-x64-setup.exe"
    assert setup.is_file() and setup.stat().st_size > 0


def test_longest_path_counts_inno_temporary_name(tools, packaging_copy: Path):
    """Un nome corto conta come il nome temporaneo di Inno (17 caratteri),
    uno più lungo conta per sé: entrambi devono stare sotto MAX_PATH."""
    build_installer, _ = tools
    app = packaging_copy / "dist" / "StemForge"
    folder = len(str(Path(_FAKE_DEEP_FILE).parent))
    assert build_installer.longest_relative_path(app) == folder + 1 + build_installer.INNO_TEMP_NAME_CHARS
    long_name = Path(_FAKE_DEEP_FILE).parent / ("n" * 40 + ".dll")
    (app / long_name).write_bytes(b"dll finta")
    assert build_installer.longest_relative_path(app) == len(str(long_name))


def _iscc_raw(iscc: Path, iss: Path, *defines: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(iscc), "/Q", "/O-", *defines, str(iss)],
                          capture_output=True, text=True, errors="replace", timeout=_COMPILE_TIMEOUT_S)


def test_compile_without_longest_path_is_refused(tools, packaging_copy: Path):
    """Senza la misura la protezione sui percorsi lunghi sarebbe spenta in silenzio."""
    _, iscc = tools
    proc = _iscc_raw(iscc, packaging_copy / "windows" / "stemforge.iss", "/DAppVersion=1.2.3")
    assert proc.returncode != 0
    assert "LongestRelPath" in proc.stdout + proc.stderr


def test_compiler_rejects_a_broken_code_section(tools, packaging_copy: Path):
    """Il primo test può fallire davvero: un [Code] rotto non compila."""
    build_installer, iscc = tools
    iss = packaging_copy / "windows" / "stemforge.iss"
    text = iss.read_text(encoding="utf-8-sig").replace("UninstallSilent()", "UninstallSilenzioso()")
    iss.write_text(text, encoding="utf-8-sig")
    with pytest.raises(RuntimeError, match="ISCC uscito"):
        build_installer.compile_installer(iscc, packaging_copy, "1.2.3")
