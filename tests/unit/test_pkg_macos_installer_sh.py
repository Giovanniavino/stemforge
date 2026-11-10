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
