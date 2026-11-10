"""Dove vivono i dati per piattaforma (§9.2) e quali opzioni si mostrano (§12-M6).

La piattaforma si simula PASSANDOLA a engine/paths.py, mai cambiando
`os.name` o `sys.platform` per tutto il processo: su macOS un `os.name`
finto fa creare a pathlib dei WindowsPath e pytest crolla con
INTERNALERROR (CI macos-15-intel, 09-11-2026).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from stemforge.engine import paths

_REAL_OS_NAME = os.name
_REAL_SYS_PLATFORM = sys.platform
TESTS = Path(__file__).resolve().parents[1]


def _assert_process_untouched() -> None:
    assert os.name == _REAL_OS_NAME, "un test ha cambiato os.name per tutto il processo"
    assert sys.platform == _REAL_SYS_PLATFORM, "un test ha cambiato sys.platform"


def test_windows_uses_local_not_roaming_appdata(tmp_path):
    # ~1 GB di modelli NON devono viaggiare col profilo Roaming
    env = {"LOCALAPPDATA": str(tmp_path / "Local"), "APPDATA": str(tmp_path / "Roaming")}
    local = tmp_path / "Local" / "StemForge"
    assert paths.models_dir("win32", env, tmp_path) == local / "models"
    assert paths.calibration_path("win32", env, tmp_path) == local / "calibration.json"
    assert paths.log_dir("win32", env, tmp_path) == local / "logs"
    _assert_process_untouched()


def test_windows_without_localappdata_falls_back_to_local_not_roaming(tmp_path):
    env = {"APPDATA": str(tmp_path / "Roaming")}
    expected = tmp_path / "AppData" / "Local" / "StemForge"
    assert paths.data_dir("win32", env, tmp_path) == expected
    _assert_process_untouched()


def test_macos_uses_application_support(tmp_path):
    expected = tmp_path / "Library" / "Application Support" / "StemForge" / "models"
    assert paths.models_dir("darwin", {}, tmp_path) == expected
    assert paths.log_dir("darwin", {}, tmp_path) == tmp_path / "Library" / "Logs" / "StemForge"
    _assert_process_untouched()


def test_linux_follows_xdg(tmp_path):
    assert paths.data_dir("linux", {}, tmp_path) == tmp_path / ".local" / "share" / "stemforge"
    env = {"XDG_DATA_HOME": str(tmp_path / "xdg")}
    assert paths.data_dir("linux", env, tmp_path) == tmp_path / "xdg" / "stemforge"
    assert paths.log_dir("linux", env, tmp_path) == tmp_path / ".local" / "state" / "stemforge"
    _assert_process_untouched()


def test_env_overrides_win_everywhere(tmp_path):
    env = {"STEMFORGE_MODELS": str(tmp_path / "m"), "STEMFORGE_CALIBRATION": str(tmp_path / "c.json")}
    for platform in ("win32", "darwin", "linux"):
        assert paths.models_dir(platform, env, tmp_path) == tmp_path / "m"
        assert paths.calibration_path(platform, env, tmp_path) == tmp_path / "c.json"


def test_defaults_read_the_real_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("STEMFORGE_MODELS", str(tmp_path / "m"))
    monkeypatch.setenv("STEMFORGE_CALIBRATION", str(tmp_path / "c.json"))
    assert paths.models_dir() == tmp_path / "m"
    assert paths.calibration_path() == tmp_path / "c.json"


_GLOBAL_PLATFORM_PATCH = re.compile(
    r"setattr\(\s*[\w.]*\b(?:os\s*,\s*[\"']name[\"']|sys\s*,\s*[\"']platform[\"'])"
)


def test_no_test_patches_the_platform_globally():
    # Su Windows os.name vale già "nt": il crash si vedrebbe solo in CI
    # macOS. Questo controllo lo fa fallire OVUNQUE, subito.
    offenders = [
        str(path.relative_to(TESTS))
        for path in TESTS.rglob("*.py")
        if _GLOBAL_PLATFORM_PATCH.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"monkeypatch globale di os.name/sys.platform in: {offenders}"


def test_unadopted_derived_backends_are_not_available():
    # finché un modello di 2° stadio non è adottato (WEIGHTS_SHA256 None)
    # l'opzione non esiste per l'utente
    from stemforge.engine.registry import is_available

    assert is_available("demucs4")
    for name in ("drumsplit", "vocalsplit", "dereverb"):
        module = __import__(f"stemforge.engine.{name}", fromlist=["WEIGHTS_SHA256"])
        assert is_available(name) == (module.WEIGHTS_SHA256 is not None)
    assert not is_available("inesistente")
