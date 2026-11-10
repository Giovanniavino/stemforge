"""Il motore con le due pile di torch, 2.2.2 e 2.10 (BUILD_SPEC D7, §10.6).

Marcati `compat`: girano in ogni ambiente (il giro normale li include) e
il job "compat" della CI li esegue di proposito sia con la pila
`legacy-intel` sia con quella moderna. Servono a scoprire in pochi
secondi, senza scaricare un GB di pesi, se un cambio di API di torch o
torchaudio rompe il percorso numerico vero: STFT complessa di HTDemucs,
`apply_model` a segmenti, hook di avanzamento/annullo, esecuzione
parziale del bag (§5.1.1), resampling sinc (§5.7).

Il modello è un HTDemucs minuscolo con pesi casuali ma fissati dal seed:
la numerica non dice niente sulla qualità, dice che il codice gira e
rispetta i contratti con QUESTA versione di torch.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("demucs")

from stemforge.engine import audio_io, demucs4  # noqa: E402
from stemforge.engine.contract import CancelledError, effective_quality  # noqa: E402
from stemforge.model.stem import StemKind as K  # noqa: E402
from tests.conftest import synth_mix  # noqa: E402

pytestmark = pytest.mark.compat

_SOURCES = ["drums", "bass", "other", "vocals"]
_SECONDS = 1.3  # più di un segmento: esercita lo split e l'overlap-add
_SEGMENT_S = 1
_SEED = 1234
# il resampling sinc andata/ritorno 44.1k -> 48k -> 44.1k su un mix
# limitato in banda deve restare molto sotto l'invariante di §10.2
_RESAMPLE_MAX_DBFS = -40.0


def _tiny_htdemucs():
    from demucs.htdemucs import HTDemucs

    return HTDemucs(
        _SOURCES, channels=8, depth=2, nfft=512, t_layers=1, t_heads=2,
        dconv_depth=1, segment=_SEGMENT_S,
    ).eval()


def _tiny_bag():
    """Bag one-hot come htdemucs_ft: il secondo modello fa solo la voce."""
    from demucs.apply import BagOfModels

    torch.manual_seed(_SEED)
    first, second = _tiny_htdemucs(), _tiny_htdemucs()
    return BagOfModels(
        [first, second], weights=[[1, 1, 1, 0], [0, 0, 0, 1]], segment=_SEGMENT_S,
    )


@pytest.fixture()
def backend(monkeypatch):
    monkeypatch.setattr(demucs4, "_load_model", lambda name: _tiny_bag())
    torch.set_num_threads(1)  # tempi stabili su una macchina condivisa
    return demucs4.Demucs4Backend("htdemucs_ft", "cpu", effective_quality("fast", "cpu"))


def _audio():
    mix = synth_mix(44100, seconds=_SECONDS)
    return torch.from_numpy(mix)


def test_tiny_model_keeps_length_and_is_finite(backend):
    audio = _audio()
    progress: list[float] = []
    out = backend.separate(
        audio, frozenset({K.VOCALS, K.DRUMS}), progress.append, lambda: False,
    )
    assert set(out) == {K.VOCALS, K.DRUMS}
    for kind, stem in out.items():
        assert tuple(stem.shape) == tuple(audio.shape), f"{kind}: campioni persi o aggiunti"
        assert stem.dtype == torch.float32
        assert bool(torch.isfinite(stem).all()), f"{kind}: valori non finiti"
    assert progress, "nessun avanzamento: gli hook di forward non scattano più"
    assert progress == sorted(progress) and progress[-1] <= 1.0


def test_partial_bag_equals_full_bag(backend):
    """§5.1.1 con il torch installato: il sotto-bag dà la stessa voce."""
    audio = _audio()
    assert backend.submodel_count(frozenset({K.VOCALS})) == 1
    assert backend.submodel_count(frozenset({K.VOCALS, K.BASS})) == 2
    partial = backend.separate(audio, frozenset({K.VOCALS}), lambda p: None, lambda: False)
    full = backend.separate(
        audio, frozenset({K.VOCALS, K.DRUMS, K.BASS, K.OTHER}), lambda p: None, lambda: False,
    )
    np.testing.assert_allclose(
        partial[K.VOCALS].numpy(), full[K.VOCALS].numpy(), rtol=0, atol=1e-5,
    )


def test_cancel_between_segments(backend):
    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] > 1  # il primo segmento passa, il secondo no

    with pytest.raises(CancelledError):
        backend.separate(_audio(), frozenset({K.VOCALS}), lambda p: None, should_cancel)


def test_sinc_resample_roundtrip_keeps_length_and_signal():
    mix = synth_mix(44100, seconds=_SECONDS)
    up = audio_io.resample(mix, 44100, 48000)
    assert up.shape[-1] == round(mix.shape[-1] * 48000 / 44100)
    back = audio_io.match_length(audio_io.resample(up, 48000, 44100), mix.shape[-1])
    assert back.dtype == np.float32 and back.shape == mix.shape
    # i bordi risentono del filtro: si confronta la parte centrale
    edge = 2048
    residual = back[:, edge:-edge] - mix[:, edge:-edge]
    rms = float(np.sqrt(np.mean(np.square(residual))))
    assert 20.0 * np.log10(max(rms, 1e-12)) < _RESAMPLE_MAX_DBFS
