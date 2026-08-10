"""Benchmark di scalabilità (§6.3): i RAPPORTI sono vincolanti, i tempi
assoluti sono solo informazione (si stampano nel report).

Marcato slow: inferenza reale su CPU con i pesi veri.
"""

from __future__ import annotations

import time

import pytest

torch = pytest.importorskip("torch")

from stemforge.engine.contract import effective_quality  # noqa: E402
from stemforge.model.stem import StemKind as K  # noqa: E402
from tests.conftest import synth_mix  # noqa: E402

SCALING_LIMIT = 0.35  # tempo(1 stem) / tempo(4 stem) in `balanced` (O7)


def _run(backend, audio, wanted) -> float:
    started = time.perf_counter()
    backend.separate(
        audio, frozenset(wanted),
        on_progress=lambda p: None, should_cancel=lambda: False,
    )
    return time.perf_counter() - started


@pytest.mark.slow
def test_single_stem_scales(monkeypatch, capsys):
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    from stemforge.engine.demucs4 import Demucs4Backend

    quality = effective_quality("balanced", "cpu")
    backend = Demucs4Backend("htdemucs_ft", "cpu", quality)
    audio = torch.from_numpy(synth_mix(44100, seconds=30.0))

    _run(backend, audio, {K.VOCALS})  # warm-up: cache, allocazioni
    one = _run(backend, audio, {K.VOCALS})
    four = _run(backend, audio, {K.VOCALS, K.DRUMS, K.BASS, K.OTHER})
    ratio = one / four
    with capsys.disabled():
        print(
            f"\n[perf] 30 s di audio, balanced/cpu: "
            f"1 stem = {one:.1f} s, 4 stem = {four:.1f} s, rapporto = {ratio:.2f}"
        )
    assert ratio < SCALING_LIMIT, f"la scalabilità O7 è persa: {ratio:.2f}"
