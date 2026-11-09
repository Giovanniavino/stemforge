"""Dove vivono i dati per piattaforma (§9.2) e quali opzioni si mostrano (§12-M6)."""

from __future__ import annotations

import sys
from pathlib import Path

from stemforge.engine import paths


def test_windows_uses_local_not_roaming_appdata(monkeypatch, tmp_path):
    # ~1 GB di modelli NON devono viaggiare col profilo Roaming
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    monkeypatch.delenv("STEMFORGE_CALIBRATION", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(paths.os, "name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert paths.models_dir() == tmp_path / "Local" / "StemForge" / "models"
    assert paths.calibration_path() == tmp_path / "Local" / "StemForge" / "calibration.json"


def test_macos_uses_application_support(monkeypatch):
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    expected = Path.home() / "Library" / "Application Support" / "StemForge" / "models"
    assert paths.models_dir() == expected


def test_env_overrides_win_everywhere(monkeypatch, tmp_path):
    monkeypatch.setenv("STEMFORGE_MODELS", str(tmp_path / "m"))
    monkeypatch.setenv("STEMFORGE_CALIBRATION", str(tmp_path / "c.json"))
    assert paths.models_dir() == tmp_path / "m"
    assert paths.calibration_path() == tmp_path / "c.json"


def test_unadopted_derived_backends_are_not_available():
    # finché un modello di 2° stadio non è adottato (WEIGHTS_SHA256 None)
    # l'opzione non esiste per l'utente
    from stemforge.engine.registry import is_available

    assert is_available("demucs4")
    for name in ("drumsplit", "vocalsplit", "dereverb"):
        module = __import__(f"stemforge.engine.{name}", fromlist=["WEIGHTS_SHA256"])
        assert is_available(name) == (module.WEIGHTS_SHA256 is not None)
    assert not is_available("inesistente")
