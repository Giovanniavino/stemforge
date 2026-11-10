"""engine/ffmpeg.py senza eseguire ffmpeg: dove lo cerca e come lo lancia (D9)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from stemforge.engine import ffmpeg


def _fake_exe(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / ffmpeg._exe_name()
    exe.write_bytes(b"#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Nessuna build di sviluppo, nessuna variabile, nessun pacchetto."""
    monkeypatch.setattr(ffmpeg, "_DEV_OUT", tmp_path / "dev-out")
    monkeypatch.delenv(ffmpeg.ENV_VAR, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    return tmp_path


def test_locate_never_uses_system_path(isolated, monkeypatch):
    # un ffmpeg (magari GPL) dell'utente nel PATH non deve entrare in gioco
    on_path = _fake_exe(isolated / "user-bin")
    monkeypatch.setenv("PATH", f"{on_path.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.chdir(on_path.parent)
    assert ffmpeg.locate() is None


def test_locate_uses_env_var_file_or_folder(isolated, monkeypatch):
    exe = _fake_exe(isolated / "custom")
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(exe))
    assert ffmpeg.locate() == exe
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(exe.parent))
    assert ffmpeg.locate() == exe


def test_locate_ignores_broken_env_var_and_falls_back_to_dev(isolated, monkeypatch):
    dev = _fake_exe(isolated / "dev-out" / ffmpeg._dev_profile())
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(isolated / "non-esiste" / "ffmpeg"))
    assert ffmpeg.locate() == dev


def test_env_var_wins_over_dev_build(isolated, monkeypatch):
    _fake_exe(isolated / "dev-out" / ffmpeg._dev_profile())
    exe = _fake_exe(isolated / "custom")
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(exe))
    assert ffmpeg.locate() == exe


def test_frozen_bundle_wins_and_dev_build_is_ignored(isolated, monkeypatch):
    bundled = _fake_exe(isolated / "meipass" / "ffmpeg")
    _fake_exe(isolated / "dev-out" / ffmpeg._dev_profile())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(isolated / "meipass"), raising=False)
    monkeypatch.setattr(sys, "executable", str(isolated / "app" / "StemForge"))
    assert ffmpeg.locate() == bundled
    bundled.unlink()
    # congelato: la build di sviluppo nei sorgenti non esiste per l'utente
    assert ffmpeg.locate() is None


def test_frozen_next_to_executable(isolated, monkeypatch):
    beside = _fake_exe(isolated / "app")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(isolated / "app" / "StemForge.exe"))
    assert ffmpeg.locate() == beside


def test_dev_profile_matches_build_profiles():
    assert ffmpeg._dev_profile() in {"legacy-intel", "mac-arm64", "win-x64", "linux-x64"}
    if sys.platform == "win32":
        assert ffmpeg._dev_profile() == "win-x64"
        assert ffmpeg._exe_name() == "ffmpeg.exe"


def test_missing_ffmpeg_raises_clear_error(isolated, tmp_path):
    with pytest.raises(ffmpeg.FfmpegMissing, match="reinstalla"):
        ffmpeg.decode(tmp_path / "brano.m4a")
    with pytest.raises(ffmpeg.FfmpegMissing):
        ffmpeg.probe_duration(tmp_path / "brano.m4a")


class _Captured(Exception):
    pass


def test_run_uses_argument_list_and_no_console_window(isolated, monkeypatch):
    exe = _fake_exe(isolated / "custom")
    monkeypatch.setenv(ffmpeg.ENV_VAR, str(exe))
    seen: dict = {}

    def fake_popen(args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        raise _Captured

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with pytest.raises(_Captured):
        ffmpeg.probe_duration(Path("pipe:brano; rm -rf ~.m4a"))
    assert isinstance(seen["args"], list) and seen["args"][0] == str(exe)
    assert not seen["kwargs"].get("shell", False)
    assert "-nostdin" in seen["args"]
    # il nome passa come file: ed e' assoluto, mai interpretato come protocollo
    source = seen["args"][seen["args"].index("-i") + 1]
    assert source.startswith("file:") and Path(source[5:]).is_absolute()
    if sys.platform == "win32":
        assert seen["kwargs"]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_wav_header_parser_reads_extensible_fmt():
    fmt = (b"fmt " + (40).to_bytes(4, "little") + (0xFFFE).to_bytes(2, "little")
           + (6).to_bytes(2, "little") + (96000).to_bytes(4, "little") + bytes(32))
    data = b"RIFF" + bytes(4) + b"WAVE" + b"LIST" + (3).to_bytes(4, "little") + b"abc\0" + fmt
    assert ffmpeg._parse_wav_header(data) == (6, 96000)
    assert ffmpeg._parse_wav_header(b"not a wav at all") is None


def test_encode_fixture_rejects_unknown_codec_and_shape(tmp_path):
    with pytest.raises(ValueError, match="codec"):
        ffmpeg.encode_fixture(np.zeros((2, 10), np.float32), 44100, tmp_path / "x.mp3", "mp3")
    with pytest.raises(ValueError, match="channels, frames"):
        ffmpeg.encode_fixture(np.zeros(10, np.float32), 44100, tmp_path / "x.flac", "flac")


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Stream #0:0[0x1](und): Audio: none (drms / 0x736D7264), 44100 Hz", "DRM"),
        ("Stream #0:0: Video: h264, yuv420p\nStream map '0:a:0' matches no streams.",
         "non contiene una traccia audio"),
        ("file:x.m4a: Invalid data found when processing input", "danneggiato"),
        # il nome del file finisce in stderr: "Encrypted" nel titolo non e' DRM
        ("Input #0, mov, from 'file:C:/Encrypted (drms / 0x1) enca.m4a':\n"
         "Stream #0:0: Audio: aac (mp4a / 0x6134706D)\nError while decoding",
         "danneggiato"),
    ],
)
def test_user_error_messages(stderr, expected):
    error = ffmpeg._user_error(Path("x.m4a"), stderr)
    assert isinstance(error, ffmpeg.DecodeError) and isinstance(error, ValueError)
    assert expected in str(error) and "x.m4a" in str(error)
