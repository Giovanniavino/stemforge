"""§5.1.1 con Demucs reale: il sotto-modello equivale all'insieme.

Marcato slow: scarica i pesi veri (~1 GB) e fa inferenza CPU.
Eseguire con: pytest -m slow tests/integration/test_single_source.py
"""

from __future__ import annotations

import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from stemforge.engine.contract import effective_quality  # noqa: E402
from stemforge.model.stem import StemKind as K  # noqa: E402
from tests.conftest import synth_mix  # noqa: E402

EQUIVALENCE_LIMIT_DBFS = -25.0


@pytest.mark.slow
def test_submodel_matches_full_ensemble(monkeypatch):
    # i pesi veri vanno nella cache di sistema, non nel tmp del test
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    from stemforge.engine.demucs4 import Demucs4Backend

    quality = effective_quality("balanced", "cpu")
    backend = Demucs4Backend("htdemucs_ft", "cpu", quality)
    audio = torch.from_numpy(synth_mix(44100))

    partial = backend.separate(
        audio, frozenset({K.VOCALS}),
        on_progress=lambda p: None, should_cancel=lambda: False,
    )
    assert backend.submodel_count(frozenset({K.VOCALS})) < 4, (
        "il bag ft deve permettere l'esecuzione parziale (§5.1.1)"
    )
    full = backend.separate(
        audio, frozenset({K.VOCALS, K.DRUMS, K.BASS, K.OTHER}),
        on_progress=lambda p: None, should_cancel=lambda: False,
    )
    diff = (partial[K.VOCALS] - full[K.VOCALS]).numpy()
    rms = float(np.sqrt(np.mean(np.square(diff))))
    rms_dbfs = -120.0 if rms == 0 else 20.0 * math.log10(rms)
    assert rms_dbfs < EQUIVALENCE_LIMIT_DBFS, (
        f"sotto-modello e insieme differiscono di {rms_dbfs:.1f} dBFS RMS"
    )
