"""Preset qualità (§5.6) e risoluzione device (§4.2, D8)."""

from __future__ import annotations

import json

import pytest

from stemforge.engine.contract import DEFAULT_QUALITY, PRESETS, effective_quality
from stemforge.engine.device import resolve_device, unverified_accelerators


def test_default_is_best():
    # la qualità viene prima del tempo: scelta del committente (§0)
    assert DEFAULT_QUALITY == "best"


def test_best_has_no_shortcuts():
    best = PRESETS["best"]
    assert best.shifts == 2
    assert best.overlap == 0.25
    assert best.half is False


@pytest.mark.parametrize("device", ["cpu", "mps"])
def test_fp16_only_on_cuda(device):
    # §5.6: su CPU è emulato, su MPS la validazione D8 confronta fp32 con fp32
    for preset in PRESETS:
        assert effective_quality(preset, device).half is False


def test_fp16_kept_on_cuda_where_preset_says_so():
    assert effective_quality("balanced", "cuda").half is True
    assert effective_quality("best", "cuda").half is False


def test_segment_is_fixed_everywhere():
    assert {q.segment_s for q in PRESETS.values()} == {7.8}


def _probes(cuda: bool = False, mps: bool = False, ok: dict | None = None) -> dict:
    """Sonde iniettate: i test unitari non toccano torch né device.json.

    `ok` = verdetti salvati per acceleratore; assente = mai verificato."""
    verdicts = ok or {}
    return {
        "cuda_available": lambda: cuda,
        "mps_available": lambda: mps,
        "verdict": lambda accelerator: verdicts.get(accelerator),
    }


@pytest.mark.parametrize("accelerator", ["cuda", "mps"])
def test_auto_uses_an_accelerator_only_after_positive_verdict(accelerator):
    # D8, per OGNI acceleratore: mai sulla fiducia
    present = {accelerator: True}
    assert resolve_device("auto", **_probes(**present, ok={accelerator: True})) == accelerator
    assert resolve_device("auto", **_probes(**present, ok={accelerator: False})) == "cpu"
    assert resolve_device("auto", **_probes(**present)) == "cpu"


def test_auto_ignores_a_verdict_for_an_absent_accelerator():
    # device.json copiato da un'altra macchina: senza la GPU il verdetto non conta
    assert resolve_device("auto", **_probes(ok={"cuda": True, "mps": True})) == "cpu"


def test_auto_prefers_cuda_when_both_are_validated():
    both = {"cuda": True, "mps": True}
    assert resolve_device("auto", **_probes(**both, ok={"cuda": True, "mps": True})) == "cuda"
    # CUDA bocciata: si passa al successivo validato, non alla CPU
    assert resolve_device("auto", **_probes(**both, ok={"cuda": False, "mps": True})) == "mps"


@pytest.mark.parametrize("accelerator", ["cuda", "mps"])
def test_forcing_an_accelerator_skips_the_verdict_but_needs_the_hardware(accelerator):
    # l'utente può forzare (D8), ma non un dispositivo che non c'è
    forced = resolve_device(accelerator, **_probes(**{accelerator: True}, ok={accelerator: False}))
    assert forced == accelerator
    with pytest.raises(RuntimeError) as info:
        resolve_device(accelerator, **_probes())
    assert info.value.key == "err.device_unavailable"


def test_device_cpu_is_cpu():
    assert resolve_device("cpu", **_probes(cuda=True, mps=True, ok={"cuda": True, "mps": True})) == "cpu"


def test_device_unknown_rejected():
    with pytest.raises(ValueError):
        resolve_device("tpu", **_probes())


def test_unverified_lists_only_present_accelerators_without_verdict():
    assert unverified_accelerators(**_probes(cuda=True, mps=True)) == ("cuda", "mps")
    assert unverified_accelerators(**_probes(cuda=True, mps=True, ok={"cuda": False})) == ("mps",)
    assert unverified_accelerators(**_probes(cuda=False, mps=False)) == ()


@pytest.mark.parametrize("accelerator", ["cuda", "mps"])
def test_verdict_roundtrip_per_accelerator(accelerator):
    from stemforge.engine import device

    other = "mps" if accelerator == "cuda" else "cuda"
    assert device.load_verdict(accelerator) is None
    device.save_verdict(accelerator, False, "scarto -12 dB")
    assert device.load_verdict(accelerator) is False
    device.save_verdict(accelerator, True, "scarto -95 dB")
    assert device.load_verdict(accelerator) is True
    assert device.load_verdict(other) is None, "un verdetto non vale per l'altro acceleratore"


def test_verdict_rejects_unknown_accelerator():
    from stemforge.engine import device

    with pytest.raises(ValueError):
        device.save_verdict("directml", True, "")


def test_v23_mps_verdict_is_still_read():
    # device.json della v2.3 sul Mac di chi aggiorna: il verdetto non si perde
    from stemforge.engine import device

    device.verdict_path().parent.mkdir(parents=True, exist_ok=True)
    device.verdict_path().write_text(json.dumps({"mps_ok": True, "detail": "x"}), encoding="utf-8")
    assert device.load_verdict("mps") is True
    assert device.load_verdict("cuda") is None


def test_corrupt_device_json_means_no_verdict():
    from stemforge.engine import device

    device.verdict_path().parent.mkdir(parents=True, exist_ok=True)
    device.verdict_path().write_text("{non json", encoding="utf-8")
    assert device.load_verdict("cuda") is None
    device.save_verdict("cuda", True, "ok")  # e si riscrive pulito
    assert device.load_verdict("cuda") is True
