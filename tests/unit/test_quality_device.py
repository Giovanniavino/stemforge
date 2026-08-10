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


def test_device_auto_prefers_cuda():
    assert resolve_device("auto", cuda_available=lambda: True) == "cuda"
    assert resolve_device("auto", cuda_available=lambda: False) == "cpu"


def test_device_cuda_requires_cuda():
    with pytest.raises(RuntimeError):
        resolve_device("cuda", cuda_available=lambda: False)


def test_device_cpu_is_cpu():
    assert resolve_device("cpu", cuda_available=lambda: True) == "cpu"


def test_device_unknown_rejected():
    with pytest.raises(ValueError):
        resolve_device("mps")
