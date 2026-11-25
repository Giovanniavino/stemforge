"""Collaudo (§10.5, D9): il controllo "FFmpeg presente e LGPL" con un FFmpeg finto."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from stemforge.worker import selftest

LGPL = (
    "configuration: --disable-everything --enable-decoder=aac,alac\n"
    "This library is free software; you can redistribute it under the terms "
    "of the GNU Lesser General Public License version 2.1 or later."
)


def _install(monkeypatch, info: str, located: bool = True) -> None:
    fake = types.ModuleType("stemforge.engine.ffmpeg")
    fake.locate = lambda: Path("ffmpeg") if located else None
    fake.license_info = lambda: info
    monkeypatch.setitem(sys.modules, "stemforge.engine.ffmpeg", fake)


def test_lgpl_build_passes(monkeypatch):
    _install(monkeypatch, LGPL)
    assert selftest._run_check("lic", selftest._check_ffmpeg_license).status == "ok"


@pytest.mark.parametrize("flag", ["--enable-gpl", "--enable-nonfree"])
def test_gpl_or_nonfree_build_fails(monkeypatch, flag):
    _install(monkeypatch, LGPL.replace("--disable-everything", f"--disable-everything {flag}"))
    assert selftest._run_check("lic", selftest._check_ffmpeg_license).status == "fail"


def test_unknown_license_fails(monkeypatch):
    _install(monkeypatch, "configuration: --disable-everything")
    assert selftest._run_check("lic", selftest._check_ffmpeg_license).status == "fail"


def test_missing_binary_is_skip_from_sources_and_fail_in_package(monkeypatch):
    _install(monkeypatch, LGPL, located=False)
    assert selftest._run_check("lic", selftest._check_ffmpeg_license).status == "skip"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert selftest._run_check("lic", selftest._check_ffmpeg_license).status == "fail"
