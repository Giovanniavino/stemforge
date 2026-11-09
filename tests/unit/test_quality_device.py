"""Preset qualità (§5.6) e risoluzione device (§4.2)."""

from __future__ import annotations

import pytest

from stemforge.engine.contract import DEFAULT_QUALITY, PRESETS, effective_quality
from stemforge.engine.device import resolve_device


def test_default_is_best():
    # la qualità viene prima del tempo: scelta del committente (§0)
    assert DEFAULT_QUALITY == "best"


def test_best_has_no_shortcuts():
    best = PRESETS["best"]
    assert best.shifts == 2
    assert best.overlap == 0.25
    assert best.half is False


def test_fp16_forced_off_on_cpu():
    for preset in PRESETS:
        assert effective_quality(preset, "cpu").half is False


def test_fp16_kept_on_cuda_where_preset_says_so():
    assert effective_quality("balanced", "cuda").half is True
    assert effective_quality("best", "cuda").half is False


def test_segment_is_fixed_everywhere():
    assert {q.segment_s for q in PRESETS.values()} == {7.8}


def _probes(cuda: bool = False, mps: bool = False, verdict: bool | None = None) -> dict:
    """Sonde iniettate: i test unitari non toccano torch."""
    return {
        "cuda_available": lambda: cuda,
        "mps_available": lambda: mps,
        "mps_verdict": lambda: verdict,
    }


def test_device_auto_prefers_cuda():
    assert resolve_device("auto", **_probes(cuda=True, mps=True, verdict=True)) == "cuda"
    assert resolve_device("auto", **_probes()) == "cpu"


def test_device_auto_uses_mps_only_after_positive_verdict():
    # Apple Silicon: la GPU si usa solo dopo che il confronto con la CPU
    # l'ha promossa — mai sulla fiducia (qualità prima del tempo, §0)
    assert resolve_device("auto", **_probes(mps=True, verdict=True)) == "mps"
    assert resolve_device("auto", **_probes(mps=True, verdict=False)) == "cpu"
    assert resolve_device("auto", **_probes(mps=True, verdict=None)) == "cpu"


def test_device_explicit_mps_requires_mps():
    assert resolve_device("mps", **_probes(mps=True)) == "mps"
    with pytest.raises(RuntimeError):
        resolve_device("mps", **_probes(mps=False))


def test_device_cuda_requires_cuda():
    with pytest.raises(RuntimeError):
        resolve_device("cuda", **_probes(cuda=False))


def test_device_cpu_is_cpu():
    assert resolve_device("cpu", **_probes(cuda=True, mps=True, verdict=True)) == "cpu"


def test_device_unknown_rejected():
    with pytest.raises(ValueError):
        resolve_device("tpu", **_probes())


def test_mps_verdict_roundtrip(tmp_path, monkeypatch):
    from stemforge.engine import device

    monkeypatch.setenv("STEMFORGE_CALIBRATION", str(tmp_path / "calibration.json"))
    assert device.load_mps_verdict() is None
    device.save_mps_verdict(False, "scarto -12 dB")
    assert device.load_mps_verdict() is False
    device.save_mps_verdict(True, "scarto -95 dB")
    assert device.load_mps_verdict() is True
