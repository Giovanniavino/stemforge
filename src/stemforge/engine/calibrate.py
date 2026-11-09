"""Calibrazione dei costi sulla macchina reale.

BUILD_SPEC §8.2.1. Le CPU Intel variano troppo per usare costanti: al
primo avvio un micro-benchmark misura i secondi di calcolo per secondo
di audio; ogni job completato affina il valore con una media mobile.
La stima in UI viene SOLO da questa tabella, mai da numeri nel codice.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from stemforge.engine import paths
from stemforge.engine.planner import DEFAULT_RATES

# Peso del valore nuovo nella media mobile esponenziale: abbastanza da
# inseguire una macchina che cambia (thermal throttling, altre app),
# abbastanza poco da non saltellare a ogni job.
_ALPHA = 0.3

_CALIBRATION_AUDIO_S = 10.0


def calibration_path() -> Path:
    return paths.calibration_path()


def load_rates() -> dict[str, float]:
    path = calibration_path()
    if not path.exists():
        return dict(DEFAULT_RATES)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_RATES)
    rates = dict(DEFAULT_RATES)
    for key, value in data.items():
        if key in rates and isinstance(value, (int, float)) and value > 0:
            rates[key] = float(value)
    return rates


def save_rates(rates: dict[str, float]) -> None:
    path = calibration_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rates, indent=2), encoding="utf-8")


def record_measurement(rate_key: str, compute_s: float, audio_s: float) -> None:
    """Aggiorna la tabella dopo una passata reale (media mobile)."""
    if audio_s <= 0 or compute_s <= 0:
        return
    rates = load_rates()
    measured = compute_s / audio_s
    old = rates.get(rate_key, DEFAULT_RATES.get(rate_key, measured))
    rates[rate_key] = (1.0 - _ALPHA) * old + _ALPHA * measured
    save_rates(rates)


_MPS_CHECK_AUDIO_S = 6.0
# Scarto massimo MPS/CPU sullo stesso audio. fp32 contro fp32 dà
# tipicamente -80 dB o meglio; -40 dB (1% d'ampiezza) è largo per gli
# arrotondamenti ma cattura qualsiasi operazione implementata male.
_MPS_MAX_ERROR_DB = -40.0


def _synthetic(seconds: float, samplerate: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed=seed)
    return (rng.standard_normal((2, int(seconds * samplerate))) * 0.1).astype(np.float32)


def _vocals_backend(device: str):
    from stemforge.engine.contract import effective_quality
    from stemforge.engine.demucs4 import Demucs4Backend

    return Demucs4Backend("htdemucs_ft", device, effective_quality("balanced", device))


def _vocals_probe(device: str, audio: np.ndarray, backend=None) -> np.ndarray:
    import torch

    from stemforge.model.stem import StemKind

    backend = backend if backend is not None else _vocals_backend(device)
    out = backend.separate(
        torch.from_numpy(audio),
        frozenset({StemKind.VOCALS}),
        on_progress=lambda _p: None,
        should_cancel=lambda: False,
    )
    return out[StemKind.VOCALS].numpy()


def validate_mps() -> bool:
    """Confronta MPS con CPU sullo stesso audio e salva il verdetto.

    Su questo controllo poggia l'uso della GPU dei Mac Apple Silicon: i
    runner di CI non hanno GPU, quindi la verifica la fa la macchina vera.
    """
    from stemforge.engine.device import save_mps_verdict

    audio = _synthetic(_MPS_CHECK_AUDIO_S, 44100, seed=1)
    try:
        reference = _vocals_probe("cpu", audio)
        candidate = _vocals_probe("mps", audio)
        error = float(np.sqrt(np.mean((candidate - reference) ** 2)))
        level = max(float(np.sqrt(np.mean(reference**2))), 1e-12)
        error_db = 20.0 * np.log10(max(error, 1e-12) / level)
        ok = bool(error_db < _MPS_MAX_ERROR_DB)
        detail = f"scarto MPS/CPU {error_db:.1f} dB (soglia {_MPS_MAX_ERROR_DB} dB)"
    except Exception as exc:  # qualsiasi guasto MPS = verdetto negativo, mai crash
        ok, detail = False, f"MPS non utilizzabile: {exc!r}"
    save_mps_verdict(ok, detail)
    return ok


def resolve_job_device(requested: str) -> str:
    """Device effettivo di un job; verifica MPS una volta sola se serve."""
    from stemforge.engine import device

    if requested == "auto" and device.mps_needs_validation():
        validate_mps()
    return device.resolve_device(requested)


def first_run_calibration(device: str) -> dict[str, float]:
    """Micro-benchmark del primo avvio (§9.4): ~10 s di audio sintetico
    attraverso il sotto-modello vocals. Restituisce la tabella salvata."""
    audio = _synthetic(_CALIBRATION_AUDIO_S, 44100, seed=0)
    backend = _vocals_backend(device)  # il caricamento dei pesi non si cronometra
    _vocals_probe(device, audio[:, :44100], backend)  # riscaldamento kernel (MPS)
    start = time.perf_counter()
    _vocals_probe(device, audio, backend)
    elapsed = time.perf_counter() - start
    rates = load_rates()
    rates["demucs4/htdemucs_ft/sub"] = elapsed / _CALIBRATION_AUDIO_S
    save_rates(rates)
    return rates
