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
    """Il 1° stadio che sull'acceleratore fallisce come un'operazione rotta."""

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


def _gpu_then_cpu(accelerator: str, error: Exception) -> tuple[dict, FakeDemucs]:
    cpu = FakeDemucs()
    cache = {
        ("demucs4", "htdemucs_ft", accelerator, "balanced"): BrokenOnGpu(error),
        ("demucs4", "htdemucs_ft", "cpu", "balanced"): cpu,
    }
    return cache, cpu


def _force_device(monkeypatch, accelerator: str) -> None:
    from stemforge.engine import calibrate

    monkeypatch.setattr(calibrate, "resolve_job_device", lambda requested: accelerator)


ACCELERATORS = ["mps", "cuda"]
# Come i due allocatori dicono "memoria finita" (testi veri di torch).
OOM_TEXT = {
    "mps": "MPS backend out of memory (MPS allocated: 7.2 GB)",
    "cuda": "CUDA out of memory. Tried to allocate 2.00 GiB",
}


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_gpu_failure_falls_back_to_cpu_and_disables_it(accelerator, mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import device
    from stemforge.worker.pipeline import run_job

    _force_device(monkeypatch, accelerator)
    cache, cpu = _gpu_then_cpu(accelerator, RuntimeError(f"{accelerator}: operazione non supportata"))
    messages, emit = collect_messages()
    result = run_job(_job(mix_44k, tmp_path), emit, backends=cache)

    assert cpu.calls, "il job deve essere stato rifatto sulla CPU"
    assert any("CPU" in w and accelerator.upper() in w for w in result.warnings)
    assert (result.out_dir / "vocals.wav").exists()
    # errore di calcolo: i job successivi partono direttamente su CPU (D8)
    assert device.load_verdict(accelerator) is False
    other = "cuda" if accelerator == "mps" else "mps"
    assert device.load_verdict(other) is None, "il verdetto è per acceleratore"
    values = [m.value for m in messages if type(m).__name__ == "Progress"]
    assert values == sorted(values), "l'avanzamento resta monotòno anche col ripiego"


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_gpu_out_of_memory_falls_back_without_disabling_it(accelerator, mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import device
    from stemforge.worker.pipeline import run_job

    _force_device(monkeypatch, accelerator)
    device.save_verdict(accelerator, True, "validato")
    cache, cpu = _gpu_then_cpu(accelerator, RuntimeError(OOM_TEXT[accelerator]))
    _messages, emit = collect_messages()
    run_job(_job(mix_44k, tmp_path), emit, backends=cache)

    assert cpu.calls
    # memoria esaurita su un brano lungo è contingente: resta promosso
    assert device.load_verdict(accelerator) is True


def test_cpu_failure_is_not_retried(mix_44k, tmp_path, monkeypatch):
    # il ripiego è per gli acceleratori: sulla CPU un errore è l'errore
    from stemforge.worker.pipeline import run_job

    _force_device(monkeypatch, "cpu")
    broken = BrokenOnGpu(RuntimeError("guasto"))
    cache = {("demucs4", "htdemucs_ft", "cpu", "balanced"): broken}
    with pytest.raises(RuntimeError, match="guasto"):
        run_job(_job(mix_44k, tmp_path), lambda m: None, backends=cache)


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_cancel_on_gpu_is_not_retried_on_cpu(accelerator, mix_44k, tmp_path, monkeypatch):
    from stemforge.engine import device
    from stemforge.worker.pipeline import run_job

    _force_device(monkeypatch, accelerator)
    cache, cpu = _gpu_then_cpu(accelerator, CancelledError("annullato"))
    _messages, emit = collect_messages()
    with pytest.raises(CancelledError):
        run_job(_job(mix_44k, tmp_path), emit, backends=cache)
    assert not cpu.calls
    assert device.load_verdict(accelerator) is None, "annullare non boccia la GPU"


def _app_ffmpeg():
    """Il FFmpeg LGPL dell'app (D9), o skip pulito se qui non è compilato.

    In CI il binario c'è (packaging/ffmpeg): lì questi test girano davvero.
    """
    ffmpeg = pytest.importorskip("stemforge.engine.ffmpeg")
    if ffmpeg.locate() is None:
        pytest.skip("FFmpeg dell'app non compilato su questa macchina (in CI c'è)")
    return ffmpeg


@pytest.mark.parametrize("codec", ["aac", "alac"])
def test_m4a_decodes_with_the_app_ffmpeg_only(codec, tmp_path, monkeypatch):
    from stemforge.engine import audio_io

    ffmpeg = _app_ffmpeg()
    t = np.arange(3 * 44100) / 44100
    tone = (0.4 * np.sin(2 * np.pi * 330.0 * t)).astype(np.float32)
    path = ffmpeg.encode_fixture(np.stack([tone, tone]), 44100, tmp_path / "brano.m4a", codec)
    monkeypatch.setenv("PATH", "")  # nessun ffmpeg di sistema raggiungibile
    source = audio_io.load(path)
    assert source.samplerate == 44100
    assert source.data.shape[0] == 2
    assert abs(source.duration_s - 3.0) < 0.1
    assert float(np.max(np.abs(source.data))) > 0.2
    assert abs(audio_io.probe_duration(path) - 3.0) < 0.1


def test_garbage_file_gives_clear_error(tmp_path):
    # con o senza il FFmpeg dell'app: un errore che dice cosa fare, mai un crash
    from stemforge.engine import audio_io
    from stemforge.worker.i18n import t

    bad = tmp_path / "rotto.m4a"
    bad.write_bytes(b"questo non e' audio" * 100)
    with pytest.raises(audio_io.UnsupportedFormatError) as info:
        audio_io.load(bad)
    assert info.value.key in ("err.corrupt", "err.ffmpeg_missing")
    assert "WAV" in t(info.value.key, **info.value.params)
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
    # dai sorgenti FFmpeg può mancare (skip); nel pacchetto è un guasto
    assert statuses["FFmpeg dell'app (LGPL)"] in ("ok", "skip")
    assert statuses["decodifica con FFmpeg (m4a, alac)"] in ("ok", "skip")
    assert statuses["separazione reale nel processo worker"] == "skip"
