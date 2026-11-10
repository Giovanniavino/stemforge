"""Zip del Mac mini (BUILD_SPEC §9.5): contenuto, permessi, fine riga.

Lo zip si costruisce su Windows e si estrae sul Mac: i bit eseguibili
valgono solo se lo zip si dichiara "fatto su Unix", e uno script con
\\r\\n non parte. Qui lo zip si costruisce davvero e si ispeziona. Che il
Mac lo estragga e lo esegua come previsto resta nella checklist manuale
(docs/manual/macos.md).
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("make_installer", ROOT / "packaging" / "make_installer.py")
mi = importlib.util.module_from_spec(_spec)
sys.modules["make_installer"] = mi
_spec.loader.exec_module(mi)

FFMPEG_ARC = "StemForge/packaging/ffmpeg/out/legacy-intel/ffmpeg"
COMUNE = ROOT / "packaging" / "installer" / "comune.sh"


def _mode(info: zipfile.ZipInfo) -> int:
    return info.external_attr >> 16


def _fake_root(tmp_path: Path) -> Path:
    """Copia minima del repo: i file obbligatori più un modulo sorgente."""
    root = tmp_path / "repo"
    names = [*mi.REQUIRED_ITEMS, *(f"{mi.INSTALLER_DIR}/{name}" for name, _ in mi.TOP_LEVEL),
             "src/stemforge/__init__.py"]
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, root / name)
    return root


def test_zip_from_the_repo_is_complete_and_unix_ready(tmp_path):
    target = tmp_path / "StemForge-Installer.zip"
    mi.build_zip(ROOT, target)
    with zipfile.ZipFile(target) as zf:
        infos = {info.filename: info for info in zf.infolist()}
        assert zf.testzip() is None
        for script in ("Installa StemForge.command", "Aggiorna StemForge.command"):
            assert infos[script].create_system == 3
            assert stat.S_IMODE(_mode(infos[script])) == 0o755
            assert zf.read(script).startswith(b"#!/bin/sh\n")
        assert stat.S_IMODE(_mode(infos["LEGGIMI.txt"])) == 0o644
        for name in ("StemForge/packaging/installer/comune.sh",
                     "StemForge/packaging/installer/requirements-build-macos-x86_64.lock",
                     "StemForge/requirements-macos-x86_64.lock",
                     "StemForge/packaging/stemforge.spec",
                     "StemForge/src/stemforge/ui/app.py"):
            assert name in infos, name
        assert zf.read("StemForge/packaging/icon.png") == (ROOT / "packaging" / "icon.png").read_bytes()
        for name, info in infos.items():
            assert stat.S_ISREG(_mode(info)), name
            assert "__pycache__" not in name and not name.startswith("StemForge/tests/")
            if mi._is_text(Path(name)):
                assert b"\r\n" not in zf.read(name), f"{name} ha fine riga Windows"
        assert not any("windows" in name or "arm64" in name for name in infos)


def test_prebuilt_ffmpeg_goes_where_spec_and_scripts_look(tmp_path):
    root = _fake_root(tmp_path)
    ffmpeg = root / mi.FFMPEG_DIR / "ffmpeg"
    ffmpeg.parent.mkdir(parents=True)
    binary = b"\xcf\xfa\xed\xfe\r\n binario: i \\r\\n non vanno toccati"
    ffmpeg.write_bytes(binary)
    (ffmpeg.parent / "LICENSE.txt").write_text("LGPL 2.1+", encoding="utf-8")
    target = tmp_path / "out.zip"
    included = mi.build_zip(root, target)
    assert [path.name for path in included] == ["ffmpeg", "LICENSE.txt"]
    with zipfile.ZipFile(target) as zf:
        assert zf.read(FFMPEG_ARC) == binary
        assert stat.S_IMODE(_mode(zf.getinfo(FFMPEG_ARC))) == 0o755
        assert "StemForge/packaging/ffmpeg/out/legacy-intel/LICENSE.txt" in zf.namelist()
    # lo spec cerca <cartella dello spec>/ffmpeg/out/<profilo>/ffmpeg ...
    spec = (ROOT / "packaging" / "stemforge.spec").read_text(encoding="utf-8")
    assert 'SPEC_DIR / "ffmpeg" / "out" / profile / name' in spec
    # ... e gli script lo preparano proprio li'
    assert 'FFMPEG_BIN="$SRC_DIR/packaging/ffmpeg/out/legacy-intel/ffmpeg"' in COMUNE.read_text(encoding="utf-8")


def test_without_ffmpeg_the_zip_is_still_built(tmp_path):
    root = _fake_root(tmp_path)
    target = tmp_path / "out.zip"
    assert mi.build_zip(root, target) == []
    with zipfile.ZipFile(target) as zf:
        assert not any("/ffmpeg/" in name for name in zf.namelist())


def test_translations_are_shipped_when_present(tmp_path):
    root = _fake_root(tmp_path)
    qm = root / "resources" / "i18n" / "stemforge_en.qm"
    qm.parent.mkdir(parents=True)
    qm.write_bytes(b"<\xb8d\x18\r\n")
    mi.build_zip(root, tmp_path / "out.zip")
    with zipfile.ZipFile(tmp_path / "out.zip") as zf:
        assert zf.read("StemForge/resources/i18n/stemforge_en.qm") == b"<\xb8d\x18\r\n"


def test_missing_build_lock_is_a_clear_error(tmp_path):
    root = _fake_root(tmp_path)
    (root / mi.INSTALLER_DIR / "requirements-build-macos-x86_64.lock").unlink()
    with pytest.raises(mi.IncompleteSourceError, match="requirements-build-macos-x86_64.lock"):
        mi.build_zip(root, tmp_path / "out.zip")


def test_installer_and_lock_tools_agree_on_sdist_exceptions():
    sys.path.insert(0, str(ROOT / "packaging"))
    try:
        import gen_locks
    finally:
        sys.path.pop(0)
    match = re.search(r'^SDIST_ONLY="([^"]+)"', COMUNE.read_text(encoding="utf-8"), re.MULTILINE)
    assert match and set(match.group(1).split(",")) == set(gen_locks.SDIST_ALLOWLIST)


def test_build_lock_pins_the_build_tools_with_hashes():
    lock = (ROOT / mi.INSTALLER_DIR / "requirements-build-macos-x86_64.lock").read_text(encoding="utf-8")
    wanted = (ROOT / "packaging" / "requirements-build.txt").read_text(encoding="utf-8")
    for package in ("pyinstaller", "pyinstaller-hooks-contrib", "pillow"):
        pin = re.search(rf"^{package}==\S+", wanted, re.MULTILINE).group(0)
        assert re.search(rf"^{re.escape(pin)} \\$", lock, re.MULTILINE), pin
    requirements = [line for line in lock.splitlines() if re.match(r"^[a-z]", line)]
    assert requirements and all(line.endswith("\\") for line in requirements)
    assert not any(line.startswith("pytest==") for line in requirements)


def test_main_reports_missing_ffmpeg(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(mi, "ROOT", _fake_root(tmp_path))
    assert mi.main(["--out", str(tmp_path / "z.zip")]) == 0
    captured = capsys.readouterr()
    assert "creato:" in captured.out and "m4a" in captured.err
