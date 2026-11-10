"""stemforge.iss compila davvero, [Code] compreso (§9.7).

Gira solo dove c'è Inno Setup (dev-box Windows, runner Windows della CI).
Non serve l'app costruita: al posto di packaging/dist/StemForge c'è un
eseguibile finto, perché qui si collauda lo script, non PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_COMPILE_TIMEOUT_S = 120


def _iscc() -> Path | None:
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    bases = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]
    for base in filter(None, bases):
        for candidate in (Path(base) / "Inno Setup 6" / "ISCC.exe", Path(base) / "Programs" / "Inno Setup 6" / "ISCC.exe"):
            if candidate.is_file():
                return candidate
    return None


@pytest.fixture()
def packaging_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Una copia di packaging/ con gli input che l'installer si aspetta."""
    pytest.importorskip("PIL")
    monkeypatch.syspath_prepend(str(ROOT / "packaging" / "windows"))
    from make_ico import make_ico

    packaging = tmp_path / "repo" / "packaging"
    (packaging / "windows").mkdir(parents=True)
    shutil.copy(ROOT / "packaging" / "windows" / "stemforge.iss", packaging / "windows")
    app = packaging / "dist" / "StemForge"
    (app / "_internal").mkdir(parents=True)
    (app / "StemForge.exe").write_bytes(b"MZ finto")
    (app / "_internal" / "dato.txt").write_text("dato", encoding="utf-8")
    make_ico(ROOT / "packaging" / "icon.png", packaging / "build" / "icon.ico")
    return packaging


@pytest.mark.skipif(sys.platform != "win32" or _iscc() is None, reason="serve Inno Setup 6 su Windows")
def test_installer_script_compiles(packaging_copy: Path):
    iss = packaging_copy / "windows" / "stemforge.iss"
    proc = subprocess.run(
        [str(_iscc()), "/Q", "/DAppVersion=1.2.3", str(iss)],
        capture_output=True, text=True, errors="replace", timeout=_COMPILE_TIMEOUT_S,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    setup = packaging_copy.parent / "dist" / "StemForge-1.2.3-windows-x64-setup.exe"
    assert setup.is_file(), list((packaging_copy.parent / "dist").iterdir())


@pytest.mark.skipif(sys.platform != "win32" or _iscc() is None, reason="serve Inno Setup 6 su Windows")
def test_compiler_rejects_a_broken_code_section(packaging_copy: Path):
    """Il test sopra può fallire davvero: un [Code] rotto non compila."""
    iss = packaging_copy / "windows" / "stemforge.iss"
    text = iss.read_text(encoding="utf-8-sig").replace("UninstallSilent()", "UninstallSilenzioso()")
    iss.write_text(text, encoding="utf-8-sig")
    proc = subprocess.run(
        [str(_iscc()), "/Q", "/O-", str(iss)],
        capture_output=True, text=True, errors="replace", timeout=_COMPILE_TIMEOUT_S,
    )
    assert proc.returncode != 0
