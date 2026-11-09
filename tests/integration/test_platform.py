"""Comportamenti nati con la distribuzione multipiattaforma (BUILD_SPEC v3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from stemforge.engine.contract import CancelledError
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K

from tests.integration.conftest import FakeDemucs, collect_messages


class BrokenOnGpu(FakeDemucs):
    """Il 1° stadio che su MPS fallisce come fallirebbe un'operazione rotta."""

    def __init__(self, error: Exception, **kwargs):
        super().__init__(**kwargs)
        self.error = error

    def separate(self, audio, wanted, on_progress, should_cancel):
        on_progress(0.3)
        raise self.error


def _job(source: Path, tmp_path: Path) -> SeparationJob:
    return SeparationJob(
        source=source, wanted=(K.VOCALS, K.OTHER), quality="balanced",
        out_dir=tmp_path / "out", device="auto",
    )


def _gpu_then_cpu(error: Exception) -> tuple[dict, FakeDemucs]:
    cpu = FakeDemucs()
    cache = {
        ("demucs4", "htdemucs_ft", "mps", "balanced"): BrokenOnGpu(error),
        ("demucs4", "htdemucs_ft", "cpu", "balanced"): cpu,
    }
    return cache, cpu


def test_gpu_failure_falls_back_to_cpu_and_disables_mps(mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import calibrate, device
    from stemforge.worker.pipeline import run_job

    monkeypatch.setattr(calibrate, "resolve_job_device", lambda requested: "mps")
    cache, cpu = _gpu_then_cpu(RuntimeError("MPS: operazione non supportata"))
    messages, emit = collect_messages()
    result = run_job(_job(mix_44k, tmp_path), emit, backends=cache)

    assert cpu.calls, "il job deve essere stato rifatto sulla CPU"
    assert any("CPU" in w for w in result.warnings)
    assert (result.out_dir / "vocals.wav").exists()
    # errore di calcolo: i job successivi partono direttamente su CPU
    assert device.load_mps_verdict() is False
    values = [m.value for m in messages if type(m).__name__ == "Progress"]
    assert values == sorted(values), "l'avanzamento resta monotòno anche col ripiego"


def test_gpu_out_of_memory_falls_back_without_disabling_mps(mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import calibrate, device
    from stemforge.worker.pipeline import run_job

    monkeypatch.setattr(calibrate, "resolve_job_device", lambda requested: "mps")
    cache, cpu = _gpu_then_cpu(RuntimeError("MPS backend out of memory"))
    _messages, emit = collect_messages()
    run_job(_job(mix_44k, tmp_path), emit, backends=cache)

    assert cpu.calls
    # memoria esaurita su un brano lungo è contingente: la GPU resta promossa
    assert device.load_mps_verdict() is None


def test_cancel_on_gpu_is_not_retried_on_cpu(mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import calibrate
    from stemforge.worker.pipeline import run_job

    monkeypatch.setattr(calibrate, "resolve_job_device", lambda requested: "mps")
    cache, cpu = _gpu_then_cpu(CancelledError("annullato"))
    _messages, emit = collect_messages()
    with pytest.raises(CancelledError):
        run_job(_job(mix_44k, tmp_path), emit, backends=cache)
    assert not cpu.calls


def _write_m4a(path: Path, seconds: float = 3.0, samplerate: int = 44100) -> Path:
    av = pytest.importorskip("av")
    t = np.arange(int(seconds * samplerate)) / samplerate
    tone = (0.4 * np.sin(2 * np.pi * 330.0 * t)).astype(np.float32)
    with av.open(str(path), "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=samplerate)
        frame = av.AudioFrame.from_ndarray(np.stack([tone, tone]), format="fltp", layout="stereo")
        frame.sample_rate = samplerate
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return path


def test_m4a_decodes_without_external_ffmpeg(tmp_path, monkeypatch):
    from stemforge.engine import audio_io

    path = _write_m4a(tmp_path / "brano.m4a")
    monkeypatch.setenv("PATH", "")  # nessun ffmpeg esterno raggiungibile
    source = audio_io.load(path)
    assert source.samplerate == 44100
    assert source.data.shape[0] == 2
    assert abs(source.duration_s - 3.0) < 0.1
    assert float(np.max(np.abs(source.data))) > 0.2
    assert abs(audio_io.probe_duration(path) - 3.0) < 0.1


def test_garbage_file_gives_clear_error(tmp_path):
    from stemforge.engine import audio_io

    bad = tmp_path / "rotto.m4a"
    bad.write_bytes(b"questo non e' audio" * 100)
    with pytest.raises(audio_io.UnsupportedFormatError):
        audio_io.load(bad)
    assert audio_io.probe_duration(bad) is None


def test_selftest_offline_passes_from_sources(tmp_path):
    """Il collaudo gira anche dai sorgenti: offline salta solo rete e modelli."""
    import json

    from stemforge.worker import selftest

    report = tmp_path / "report.json"
    code = selftest.run(report, network=False)
    data = json.loads(report.read_text(encoding="utf-8"))
    statuses = {c["name"]: c["status"] for c in data["checks"]}
    assert code == 0, data
    assert statuses["dati di demucs nel pacchetto"] == "ok"
    assert statuses["decodifica dei formati"] == "ok"
    assert statuses["separazione reale nel processo worker"] == "skip"
