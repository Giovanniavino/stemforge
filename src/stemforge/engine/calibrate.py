"""Calibrazione dei costi sulla macchina reale.

BUILD_SPEC §8.2.1. Le CPU Intel variano troppo per usare costanti: al
primo avvio un micro-benchmark misura i secondi di calcolo per secondo
di audio; ogni job completato affina il valore con una media mobile.
La stima in UI viene SOLO da questa tabella, mai da numeri nel codice.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

from stemforge.engine.planner import DEFAULT_RATES

# Peso del valore nuovo nella media mobile esponenziale: abbastanza da
# inseguire una macchina che cambia (thermal throttling, altre app),
# abbastanza poco da non saltellare a ogni job.
_ALPHA = 0.3

_CALIBRATION_AUDIO_S = 10.0


def calibration_path() -> Path:
    override = os.environ.get("STEMFORGE_CALIBRATION")
    if override:
        return Path(override)
    if os.name == "nt":  # dev-box Windows (D6)
        base = Path(os.environ["APPDATA"]) / "StemForge"
    else:
        base = Path.home() / "Library" / "Application Support" / "StemForge"
    return base / "calibration.json"


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


def first_run_calibration(device: str) -> dict[str, float]:
    """Micro-benchmark del primo avvio (§9.4): ~10 s di audio sintetico
    attraverso il sotto-modello vocals. Restituisce la tabella salvata."""
    from stemforge.engine.contract import effective_quality
    from stemforge.engine.demucs4 import Demucs4Backend
    from stemforge.model.stem import StemKind

    import torch

    quality = effective_quality("balanced", device)
    backend = Demucs4Backend("htdemucs_ft", device, quality)
    samples = int(_CALIBRATION_AUDIO_S * backend.samplerate)
    rng = np.random.default_rng(seed=0)
    audio = torch.from_numpy(
        rng.standard_normal((2, samples)).astype(np.float32) * 0.1
    )
    start = time.perf_counter()
    backend.separate(
        audio,
        frozenset({StemKind.VOCALS}),
        on_progress=lambda _p: None,
        should_cancel=lambda: False,
    )
    elapsed = time.perf_counter() - start
    rates = load_rates()
    rates["demucs4/htdemucs_ft/sub"] = elapsed / _CALIBRATION_AUDIO_S
    save_rates(rates)
    return rates
