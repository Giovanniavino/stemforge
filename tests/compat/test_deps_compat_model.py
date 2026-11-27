"""Il percorso del modello (demucs 4.0.1: STFT, convoluzioni, transformer,
apply_model a segmenti con overlap) da' gli stessi numeri con torch 2.2.2
e 2.10. Un HTDemucs minuscolo con pesi deterministici (nessun peso vero,
nessun seed di torch: l'inizializzazione casuale puo' cambiare fra
versioni) su una sinusoide generata qui."""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("demucs")

from demucs.apply import apply_model  # noqa: E402
from demucs.htdemucs import HTDemucs  # noqa: E402

pytestmark = pytest.mark.compat

SAMPLERATE = 44100
SECONDS = 2.5
OVERLAP = 0.25  # come i preset qualita' (§5.6): split + overlap, niente shifts

# Calcolati con torch 2.10.0 e 2.2.2 su Windows x64 (20-11-2026): uguali
# fino alla settima cifra. La tolleranza copre CPU diverse (AVX/NEON), non
# un operatore che cambia comportamento.
GOLDEN_SUM = 48376.77062914138
GOLDEN_ABS_SUM = 56247.28007440012
GOLDEN_DRUMS_LEFT_1000 = (0.2711699306964874, 0.3200072944164276, 0.17672987282276154)
GOLDEN_BASS_RIGHT_50000 = (-0.0331343375146389, 0.09267190098762512, 0.06694843620061874)
SUM_RTOL = 1e-4
SAMPLE_ATOL = 1e-4


def _deterministic_model() -> HTDemucs:
    model = HTDemucs(sources=["drums", "bass"], channels=8, depth=4, t_layers=1,
                     segment=Fraction(1, 1))
    with torch.no_grad():
        for index, (_, param) in enumerate(sorted(model.named_parameters())):
            fan_in = max(1, param.numel() // max(1, param.shape[0]))
            values = np.sin(np.arange(param.numel(), dtype=np.float64) * 0.37 + index)
            param.copy_(torch.from_numpy((values / np.sqrt(fan_in)).reshape(param.shape)))
    return model.eval()


def _input() -> torch.Tensor:
    t = np.arange(int(SECONDS * SAMPLERATE)) / SAMPLERATE
    left = 0.5 * np.sin(2 * np.pi * 220 * t)
    right = 0.3 * np.sin(2 * np.pi * 330 * t + 1)
    return torch.from_numpy(np.stack([left, right]).astype(np.float32))[None]


@pytest.fixture()
def one_thread():
    # un modello cosi' piccolo con piu' thread passa il tempo a sincronizzarli
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def test_tiny_htdemucs_gives_the_same_numbers_on_both_versions(one_thread):
    with torch.no_grad():
        out = apply_model(_deterministic_model(), _input(), shifts=0, split=True,
                          overlap=OVERLAP, progress=False)[0]

    assert out.shape == (2, 2, int(SECONDS * SAMPLERATE)) and out.dtype == torch.float32
    assert float(out.double().sum()) == pytest.approx(GOLDEN_SUM, rel=SUM_RTOL)
    assert float(out.double().abs().sum()) == pytest.approx(GOLDEN_ABS_SUM, rel=SUM_RTOL)
    np.testing.assert_allclose(out[0, 0, 1000:1003].numpy(), GOLDEN_DRUMS_LEFT_1000,
                               atol=SAMPLE_ATOL)
    np.testing.assert_allclose(out[1, 1, 50000:50003].numpy(), GOLDEN_BASS_RIGHT_50000,
                               atol=SAMPLE_ATOL)
