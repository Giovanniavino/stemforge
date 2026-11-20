"""packaging/ffmpeg/check_license.sh deve rifiutare un FFmpeg GPL (D9).

Il controllo gira a fine build.sh e sul runner Windows: se accettasse un
binario GPL, la regola "FFmpeg solo LGPL" non avrebbe nessuna difesa.
Qui lo si mette davanti a ffmpeg finti, uno conforme e alcuni no.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parents[2] / "packaging" / "ffmpeg"
CHECK = PACKAGING / "check_license.sh"
GIT_BASH = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe"

LGPL_CONFIG = "configuration: --disable-everything --enable-small --enable-ffmpeg"
LGPL_L = ("FFmpeg is free software; you can redistribute it and/or\r\n"
          "modify it under the terms of the GNU Lesser General Public\r\n"
          "License as published by the Free Software Foundation; either\r\n"
          "version 2.1 of the License, or (at your option) any later version.\r\n")
GPL_L = ("FFmpeg is free software; you can redistribute it and/or modify\n"
         "it under the terms of the GNU General Public License as published by\n"
         "the Free Software Foundation; either version 2 of the License, or\n")


def _posix_bash() -> str | None:
    """Un bash POSIX vero: su Windows quello di Git, mai il lanciatore di WSL."""
    found = shutil.which("bash")
    windir = os.environ.get("WINDIR", "C:/Windows").lower().replace("\\", "/")
    if found and not found.lower().replace("\\", "/").startswith(windir):
        return found
    return str(GIT_BASH) if GIT_BASH.is_file() else None


BASH = _posix_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="serve bash (Git Bash su Windows)")


def _check(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, CHECK.as_posix(), *args], capture_output=True,
                          text=True, timeout=60, check=False)


def _fake_ffmpeg(tmp_path: Path, config: str, license_text: str) -> str:
    (tmp_path / "version.txt").write_text(
        f"ffmpeg version 7.1.5 Copyright (c) 2000-2026\n{config}\n", newline="")
    (tmp_path / "license.txt").write_text(license_text, newline="")
    exe = tmp_path / "ffmpeg"
    here = tmp_path.as_posix()
    exe.write_text(
        "#!/bin/sh\n"
        f'case "$*" in *-version*) cat "{here}/version.txt" ;;'
        f' *-L*) cat "{here}/license.txt" ;; *) exit 1 ;; esac\n', newline="\n")
    exe.chmod(0o755)
    return exe.as_posix()


def test_lgpl_binary_passes(tmp_path):
    result = _check(_fake_ffmpeg(tmp_path, LGPL_CONFIG, LGPL_L))
    assert result.returncode == 0, result.stderr
    assert "LGPL 2.1" in result.stdout


@pytest.mark.parametrize(("config", "license_text"), [
    (LGPL_CONFIG + " --enable-gpl", GPL_L),
    (LGPL_CONFIG + " --enable-gpl", LGPL_L),  # -L mente, la configurazione no
    (LGPL_CONFIG + " --enable-version3", LGPL_L),
    (LGPL_CONFIG + " --enable-nonfree", LGPL_L),
    (LGPL_CONFIG, GPL_L),
    ("nessuna riga di configurazione", LGPL_L),
])
def test_non_lgpl_binary_is_rejected(tmp_path, config, license_text):
    result = _check(_fake_ffmpeg(tmp_path, config, license_text))
    assert result.returncode != 0
    assert "NON CONFORME" in result.stderr


def _fake_binary(tmp_path: Path, *strings: bytes) -> str:
    blob = tmp_path / "ffmpeg.exe"
    blob.write_bytes(b"MZ\x90\x00" + b"\x00".join(strings) + b"\x00\x01\x02")
    return blob.as_posix()


def test_static_check_reads_strings_of_a_foreign_binary(tmp_path):
    good = _fake_binary(tmp_path, b"LGPL version 2.1 or later",
                        b"--disable-everything --enable-small")
    result = _check("--static", good)
    assert result.returncode == 0, result.stderr
    assert "--disable-everything" in result.stdout


@pytest.mark.parametrize("strings", [
    (b"GPL version 2 or later", b"--disable-everything --enable-small"),
    (b"LGPL version 2.1 or later", b"GPL version 3 or later", b"--disable-everything"),
    (b"LGPL version 2.1 or later", b"--disable-everything --enable-gpl"),
    (b"LGPL version 2.1 or later", b"--enable-small"),
])
def test_static_check_rejects_gpl_strings(tmp_path, strings):
    result = _check("--static", _fake_binary(tmp_path, *strings))
    assert result.returncode != 0
    assert "NON CONFORME" in result.stderr


def test_build_flags_never_enable_gpl_nonfree_version3_or_external_libs():
    # la lista dei flag di build.sh, non il controllo che li rifiuta
    text = (PACKAGING / "build.sh").read_text(encoding="utf-8")
    flags = text.split("COMMON_FLAGS=(", 1)[1].split("\n)", 1)[0]
    for forbidden in ("--enable-gpl", "--enable-nonfree", "--enable-version3",
                      "--enable-lib"):
        assert forbidden not in flags
    for required in ("--disable-everything", "--disable-autodetect",
                     "--disable-network", "--enable-small"):
        assert required in flags
