"""packaging/installer/comune.sh eseguito davvero con sh (BUILD_SPEC §9.5).

Le funzioni che decidono cosa succede al FFmpeg incluso nello zip e che
cosa si dice all'utente non toccano niente di specifico del Mac (xattr
manca altrove ed e' gia' opzionale), quindi si eseguono con qualsiasi sh
POSIX, anche Git Bash su Windows. pip, PyInstaller, pkgutil e la copia
in /Applications restano nella checklist manuale.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMUNE = ROOT / "packaging" / "installer" / "comune.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None, reason="serve una sh POSIX (Git Bash su Windows)")


def _posix(path: Path) -> str:
    return path.as_posix()


def run_comune(src_dir: Path, body: str) -> subprocess.CompletedProcess[str]:
    script = (
        'die() { echo "DIE: $1"; exit 3; }\n'
        'SRC_DIR="$TEST_SRC"\n'
        '. "$TEST_COMUNE"\n'
        f"{body}\n"
    )
    env = {**os.environ, "TEST_SRC": _posix(src_dir), "TEST_COMUNE": _posix(COMUNE),
           "HOME": _posix(src_dir)}
    return subprocess.run([SH, "-c", script], capture_output=True, text=True, env=env, timeout=60)


def _ffmpeg(src_dir: Path, exit_code: int) -> Path:
    binary = src_dir / "packaging" / "ffmpeg" / "out" / "legacy-intel" / "ffmpeg"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(f"#!/bin/sh\nexit {exit_code}\n".encode())
    return binary


def test_without_ffmpeg_the_user_is_told_about_m4a(tmp_path):
    result = run_comune(tmp_path, 'prepare_ffmpeg; echo "STATUS=$FFMPEG_STATUS"; ffmpeg_notice')
    assert result.returncode == 0, result.stderr
    assert "STATUS=assente" in result.stdout
    assert "NON aprira' i file m4a, aac e alac" in result.stdout
    assert "lo zip non contiene il decoder FFmpeg" in result.stdout


def test_working_ffmpeg_is_kept_and_nothing_is_said(tmp_path):
    binary = _ffmpeg(tmp_path, 0)
    result = run_comune(tmp_path, 'prepare_ffmpeg; echo "STATUS=$FFMPEG_STATUS"; ffmpeg_notice')
    assert result.returncode == 0, result.stderr
    assert "STATUS=ok" in result.stdout
    assert "ATTENZIONE" not in result.stdout
    assert binary.is_file()


def test_ffmpeg_that_does_not_start_is_set_aside_and_reported(tmp_path):
    binary = _ffmpeg(tmp_path, 1)
    result = run_comune(tmp_path, 'prepare_ffmpeg; echo "STATUS=$FFMPEG_STATUS"; ffmpeg_notice')
    assert result.returncode == 0, result.stderr
    assert "STATUS=non parte" in result.stdout
    assert "non parte su questo Mac" in result.stdout
    # messo da parte: lo spec non lo trova e non lo impacchetta
    assert not binary.exists() and binary.with_name("ffmpeg.non-parte").is_file()
    # un secondo giro con lo stesso zip ricorda perche' manca
    again = run_comune(tmp_path, 'prepare_ffmpeg; echo "STATUS=$FFMPEG_STATUS"')
    assert "STATUS=non parte" in again.stdout


def test_ffmpeg_lost_during_the_build_is_reported(tmp_path):
    result = run_comune(tmp_path, 'FFMPEG_STATUS="non impacchettato"; ffmpeg_notice')
    assert "non e' entrato nell'app" in result.stdout


def test_python_check_rejects_missing_and_wrong_interpreters(tmp_path):
    good = tmp_path / "python-buono"
    good.write_bytes(b"#!/bin/sh\nexit 0\n")
    bad = tmp_path / "python-arm64"
    bad.write_bytes(b"#!/bin/sh\nexit 1\n")
    for path in (good, bad):
        path.chmod(0o755)
    body = (f'is_python311_intel "{_posix(good)}" && echo BUONO; '
            f'is_python311_intel "{_posix(bad)}" || echo SCARTATO; '
            f'is_python311_intel "{_posix(tmp_path / "manca")}" || echo ASSENTE')
    result = run_comune(tmp_path, body)
    assert result.stdout.split() == ["BUONO", "SCARTATO", "ASSENTE"]


def test_missing_lock_stops_with_a_clear_message(tmp_path):
    result = run_comune(tmp_path, "install_locked_deps")
    assert result.returncode == 3
    assert "DIE: file mancante" in result.stdout and "requirements-macos-x86_64.lock" in result.stdout


def _fake_build_env(home: Path, pyav_installed: bool) -> Path:
    """Un "python" dell'ambiente di build che registra come pip viene chiamato."""
    python = home / "Library" / "Application Support" / "StemForge" / "build-env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    show_exit = 0 if pyav_installed else 1
    python.write_bytes(
        f'#!/bin/sh\necho "$*" >> "$HOME/pip.log"\n'
        f'[ "$1 $2 $3" = "-m pip show" ] && exit {show_exit}\nexit 0\n'.encode())
    python.chmod(0o755)
    for lock in ("requirements-macos-x86_64.lock",
                 "packaging/installer/requirements-build-macos-x86_64.lock"):
        (home / lock).parent.mkdir(parents=True, exist_ok=True)
        (home / lock).write_bytes(b"")
    return home / "pip.log"


def test_locked_install_is_hash_checked_binary_only_and_drops_pyav(tmp_path):
    log = _fake_build_env(tmp_path, pyav_installed=True)
    result = run_comune(tmp_path, "install_locked_deps && echo FATTO")
    assert result.returncode == 0 and "FATTO" in result.stdout, result.stdout + result.stderr
    app_lock, build_lock, show, uninstall, own = log.read_text(encoding="utf-8").splitlines()
    assert app_lock.startswith("-m pip install --require-hashes --only-binary :all: "
                               "--no-binary antlr4-python3-runtime,demucs,dora-search -r ")
    assert app_lock.endswith("/requirements-macos-x86_64.lock")
    assert "--require-hashes --only-binary :all: -r " in build_lock
    assert build_lock.endswith("/requirements-build-macos-x86_64.lock")
    assert show == "-m pip show av" and uninstall == "-m pip uninstall --quiet --yes av"
    assert own.startswith("-m pip install --quiet ") and "--no-deps" in own


def test_without_pyav_nothing_is_uninstalled(tmp_path):
    log = _fake_build_env(tmp_path, pyav_installed=False)
    assert run_comune(tmp_path, "install_locked_deps").returncode == 0
    assert not any("uninstall" in line for line in log.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize("script", ["Installa StemForge.command", "Aggiorna StemForge.command"])
def test_both_scripts_align_to_the_lock_before_building(script):
    # Aggiorna non deve ricostruire sopra un ambiente rimasto alla versione vecchia
    text = (ROOT / "packaging" / "installer" / script).read_text(encoding="utf-8")
    steps = [text.index(f"\n{step}\n") for step in
             ("install_locked_deps", "prepare_ffmpeg", "build_app", "copy_to_applications", "ffmpeg_notice")]
    assert steps == sorted(steps)
