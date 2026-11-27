"""D8 per ogni acceleratore: la validazione contro la CPU, con sonde iniettate.

Nessuna GPU qui né nei runner di CI: la sonda che "separa" è finta e
restituisce, per device, l'uscita che un acceleratore buono, rotto o
guasto darebbe. Si verifica cosa ne fa il motore: verdetto salvato in
device.json per QUELL'acceleratore, "auto" che lo usa solo se positivo,
e una sola validazione per macchina.
"""

from __future__ import annotations

import numpy as np
import pytest

from stemforge.engine import calibrate, device

ACCELERATORS = ["cuda", "mps"]


class Probe:
    """Sonda finta: la CPU restituisce l'audio, l'acceleratore un suo errore."""

    def __init__(self, error_scale: float = 0.0, fail: Exception | None = None,
                 shape_change: bool = False) -> None:
        self.error_scale, self.fail, self.shape_change = error_scale, fail, shape_change
        self.calls: list[str] = []

    def __call__(self, device_name: str, audio: np.ndarray) -> np.ndarray:
        self.calls.append(device_name)
        if device_name == "cpu":
            return audio.copy()
        if self.fail is not None:
            raise self.fail
        if self.shape_change:
            return audio[:, :-1]
        noise = np.random.default_rng(3).standard_normal(audio.shape).astype(np.float32)
        return audio + self.error_scale * float(np.std(audio)) * noise


def _present(accelerator: str) -> dict:
    return {
        "cuda_available": lambda: accelerator == "cuda",
        "mps_available": lambda: accelerator == "mps",
    }


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_an_exact_accelerator_is_promoted(accelerator):
    probe = Probe(error_scale=1e-4)  # -80 dB: arrotondamenti fp32
    assert calibrate.validate_accelerator(accelerator, probe) is True
    assert device.load_verdict(accelerator) is True
    assert sorted(probe.calls) == ["cpu", accelerator], "confronto sullo stesso audio"


@pytest.mark.parametrize("accelerator", ACCELERATORS)
@pytest.mark.parametrize("scale", [0.02, 0.5])  # -34 dB e -6 dB: sopra la soglia di -40
def test_an_inexact_accelerator_is_refused(accelerator, scale):
    assert calibrate.validate_accelerator(accelerator, Probe(error_scale=scale)) is False
    assert device.load_verdict(accelerator) is False


@pytest.mark.parametrize("accelerator", ACCELERATORS)
@pytest.mark.parametrize("probe", [
    Probe(fail=RuntimeError("operazione non implementata")),
    Probe(shape_change=True),
], ids=["guasto", "forma-diversa"])
def test_a_broken_accelerator_is_refused_without_crashing(accelerator, probe):
    assert calibrate.validate_accelerator(accelerator, probe) is False
    assert device.load_verdict(accelerator) is False
    other = "mps" if accelerator == "cuda" else "cuda"
    assert device.load_verdict(other) is None, "il verdetto è per acceleratore"


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_auto_validates_once_then_uses_the_accelerator(accelerator):
    probe = Probe(error_scale=1e-4)
    assert calibrate.resolve_job_device("auto", probe=probe, **_present(accelerator)) == accelerator
    calls = len(probe.calls)
    assert calibrate.resolve_job_device("auto", probe=probe, **_present(accelerator)) == accelerator
    assert len(probe.calls) == calls, "una validazione per macchina, non per job"


@pytest.mark.parametrize("accelerator", ACCELERATORS)
def test_auto_stays_on_cpu_after_a_negative_verdict(accelerator):
    probe = Probe(error_scale=0.5)
    assert calibrate.resolve_job_device("auto", probe=probe, **_present(accelerator)) == "cpu"
    calls = len(probe.calls)
    assert calibrate.resolve_job_device("auto", probe=probe, **_present(accelerator)) == "cpu"
    assert len(probe.calls) == calls, "un acceleratore bocciato non si riprova a ogni job"


@pytest.mark.parametrize("requested", ["cpu", "cuda"])
def test_explicit_devices_never_run_the_validation(requested):
    probe = Probe()
    assert calibrate.resolve_job_device(requested, probe=probe, **_present("cuda")) == requested
    assert not probe.calls
    assert device.load_verdict("cuda") is None
