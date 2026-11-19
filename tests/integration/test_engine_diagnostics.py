"""Esporta diagnostica (BUILD_SPEC §9.9): lo zip e il collaudo in un processo a parte."""

from __future__ import annotations

import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from stemforge import __version__
from stemforge.engine import device
from stemforge.worker import diagnostics, launch

NOW = datetime(2026, 11, 19, 21, 30, 5)
FAKE_SELFTEST = {"ok": True, "checks": [{"name": "finto", "status": "ok", "detail": ""}]}


def _fake_selftest(workdir: Path) -> dict:
    assert workdir.is_dir(), "il collaudo riceve una cartella di lavoro temporanea"
    return dict(FAKE_SELFTEST)


def _machine_state(tmp_path: Path) -> Path:
    """calibration.json, device.json e due log ruotati, come su una macchina vera."""
    calibration = Path(os.environ["STEMFORGE_CALIBRATION"])  # isolata da conftest
    calibration.write_text(json.dumps({"demucs4/htdemucs_ft/sub": 0.42}), encoding="utf-8")
    device.save_verdict("mps", False, "scarto MPS/CPU -12.0 dB")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "stemforge.log").write_text("job su Brano è 日本.wav\n", encoding="utf-8")
    (logs / "stemforge.log.1").write_text("riga vecchia\n", encoding="utf-8")
    (logs / "altro.txt").write_text("non è un log dell'app\n", encoding="utf-8")
    return logs


def test_zip_has_log_version_system_selftest_and_verdicts(tmp_path):
    logs = _machine_state(tmp_path)
    path = diagnostics.export_diagnostics(tmp_path / "dest", _fake_selftest, logs, NOW)

    assert path == tmp_path / "dest" / "StemForge-diagnostica-20261119-213005.zip"
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert names == {"LEGGIMI.txt", "sistema.json", "selftest.json", "device.json",
                         "calibration.json", "log/stemforge.log", "log/stemforge.log.1"}
        system = json.loads(archive.read("sistema.json"))
        assert system["stemforge"] == __version__
        assert system["python"] and system["platform"] and system["machine"]
        assert system["created"] == "2026-11-19T21:30:05"
        assert json.loads(archive.read("selftest.json")) == FAKE_SELFTEST
        assert json.loads(archive.read("device.json"))["mps"]["ok"] is False
        assert json.loads(archive.read("calibration.json")) == {"demucs4/htdemucs_ft/sub": 0.42}
        assert "日本" in archive.read("log/stemforge.log").decode("utf-8")
        assert __version__ in archive.read("LEGGIMI.txt").decode("utf-8")
    assert not list((tmp_path / "dest").glob("*.part")), "nessun file provvisorio rimasto"


def test_readme_warns_about_track_names_in_the_user_language(tmp_path, monkeypatch):
    monkeypatch.setenv("STEMFORGE_LOCALE", "en")
    path = diagnostics.export_diagnostics(tmp_path, _fake_selftest, tmp_path / "nologs", NOW)
    with zipfile.ZipFile(path) as archive:
        readme = archive.read("LEGGIMI.txt").decode("utf-8")
    assert "NAMES of the tracks" in readme and "never sends" in readme


def test_a_fresh_machine_still_gets_a_zip(tmp_path):
    # niente calibrazione, verdetti né log: lo zip serve proprio lì
    path = diagnostics.export_diagnostics(tmp_path / "d", _fake_selftest, tmp_path / "nologs", NOW)
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"LEGGIMI.txt", "sistema.json", "selftest.json"}


def test_never_overwrites_a_previous_export(tmp_path):
    first = diagnostics.export_diagnostics(tmp_path, _fake_selftest, tmp_path, NOW)
    second = diagnostics.export_diagnostics(tmp_path, _fake_selftest, tmp_path, NOW)
    assert first != second and first.is_file() and second.is_file()
    assert second.name == "StemForge-diagnostica-20261119-213005 (2).zip"


def test_a_failing_zip_leaves_no_half_file(tmp_path, monkeypatch):
    def broken_info(now):
        raise RuntimeError("guasto a metà")

    monkeypatch.setattr(diagnostics, "system_info", broken_info)
    with pytest.raises(RuntimeError):
        diagnostics.export_diagnostics(tmp_path, _fake_selftest, tmp_path, NOW)
    assert list(tmp_path.iterdir()) == []


def test_selftest_that_cannot_run_is_reported_not_raised(tmp_path, monkeypatch):
    crash = [sys.executable, "-c", "import sys; print('morto al lancio'); sys.exit(3)"]
    monkeypatch.setattr(diagnostics, "selftest_command", lambda report, offline: crash)
    result = diagnostics.run_offline_selftest(tmp_path)
    assert result["ok"] is False and result["exit"] == 3
    assert "morto al lancio" in result["output"]

    monkeypatch.setattr(diagnostics, "selftest_command",
                        lambda report, offline: [str(tmp_path / "non-esiste.exe")])
    assert "non avviato" in diagnostics.run_offline_selftest(tmp_path)["error"]


def test_selftest_command_matches_the_package_entry_point(monkeypatch, tmp_path):
    report = tmp_path / "r.json"
    source = launch.selftest_command(report)
    assert source[1:3] == ["-m", "stemforge.worker.selftest"]
    assert source[-3:] == ["--report", str(report), "--offline"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # nel pacchetto: lo stesso eseguibile dell'app, che riconosce --selftest
    assert launch.selftest_command(report, offline=False) == [
        sys.executable, "--selftest", "--report", str(report)]


def test_real_offline_selftest_runs_in_a_child_process(tmp_path):
    """Il collaudo vero, lanciato come lo lancia la diagnostica."""
    result = diagnostics.run_offline_selftest(tmp_path)
    statuses = {c["name"]: c["status"] for c in result.get("checks", [])}
    assert result["ok"] is True, result
    assert result["exit"] == 0
    assert statuses["decodifica dei formati"] == "ok"
    assert statuses["separazione reale nel processo worker"] == "skip"  # --offline
