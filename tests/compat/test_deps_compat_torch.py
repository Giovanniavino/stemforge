"""Le API torch/torchaudio che il motore usa NON cambiano fra 2.2.2 e 2.10.

Ogni test qui documenta un'API censita in engine/compat.py come "uguale":
se un aggiornamento la cambia, il test fallisce e la differenza va
incapsulata in compat.py, non sparsa nel motore.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

torch = pytest.importorskip("torch")
taf = pytest.importorskip("torchaudio.functional")

from stemforge.engine import audio_io, compat  # noqa: E402

pytestmark = pytest.mark.compat

# Versioni (maggiore, minore) dei profili: legacy-intel e moderni (§2.2).
SUPPORTED_TORCH = {(2, 2), (2, 10)}

# audio_io.resample su un segnale fisso, calcolato con torch 2.10 E 2.2.2
# (identici bit per bit su Windows x64, 18-11-2026). La tolleranza copre
# solo l'arrotondamento di CPU diverse (NEON/AVX), non un kernel diverso.
GOLDEN_SUM_48K_TO_44K = -9.68599598434066
GOLDEN_LEFT_1000 = (-0.4465523, -0.47396138, -0.49177203)
GOLDEN_RIGHT_2000 = (-0.00746923, -0.13544692, -0.02891408)
GOLDEN_TOLERANCE = 1e-5

SINE_HZ = 1000.0
EDGE_SAMPLES = 256  # il filtro sinc ha bisogno di contesto ai bordi
MIN_SINE_SNR_DB = 80.0


def _golden_input() -> np.ndarray:
    rng = np.random.default_rng(7)
    t = np.arange(4800) / 48000
    left = 0.5 * np.sin(2 * np.pi * SINE_HZ * t)
    right = 0.1 * rng.standard_normal(t.size)
    return np.stack([left, right]).astype(np.float32)


def test_torch_is_one_of_the_profiles():
    # Un torch nuovo richiede di rifare il censimento di compat.py.
    assert compat.torch_version() in SUPPORTED_TORCH, torch.__version__


def test_resample_gives_the_same_numbers_on_both_versions():
    out = audio_io.resample(_golden_input(), 48000, 44100)

    assert out.shape == (2, 4410) and out.dtype == np.float32
    assert abs(float(np.sum(out.astype(np.float64))) - GOLDEN_SUM_48K_TO_44K) < 1e-3
    np.testing.assert_allclose(out[0, 1000:1003], GOLDEN_LEFT_1000, atol=GOLDEN_TOLERANCE)
    np.testing.assert_allclose(out[1, 2000:2003], GOLDEN_RIGHT_2000, atol=GOLDEN_TOLERANCE)


@pytest.mark.parametrize(("sr_from", "sr_to"), [(48000, 44100), (22050, 44100)])
def test_resample_keeps_a_sine_clean(sr_from, sr_to):
    t_in = np.arange(sr_from // 5) / sr_from
    sine = np.sin(2 * np.pi * SINE_HZ * t_in).astype(np.float32)[None, :]

    out = audio_io.resample(sine, sr_from, sr_to)[0]
    expected = np.sin(2 * np.pi * SINE_HZ * np.arange(out.size) / sr_to)
    core = slice(EDGE_SAMPLES, out.size - EDGE_SAMPLES)
    error = out[core] - expected[core]
    snr_db = 10 * np.log10(np.mean(expected[core] ** 2) / np.mean(error**2))

    assert snr_db > MIN_SINE_SNR_DB


def test_resample_accepts_the_parameters_audio_io_passes():
    params = inspect.signature(taf.resample).parameters
    for name in ("orig_freq", "new_freq", "lowpass_filter_width", "rolloff",
                 "resampling_method", "beta"):
        assert name in params
    # il nome del metodo e' cambiato nella 2.0 ("kaiser_window"): deve
    # essere accettato da entrambe, non solo non sollevare per caso
    out = taf.resample(torch.zeros(1, 64), 2, 1, resampling_method="sinc_interp_kaiser", beta=8.0)
    assert out.shape == (1, 32)


class _Cancelled(Exception):
    pass


def test_forward_pre_hook_counts_and_cancel_propagates():
    # demucs4 conta i segmenti e annulla con un pre-hook (§5.5)
    layer = torch.nn.Linear(4, 4)
    seen: list[tuple[object, int]] = []

    def hook(module, inputs):
        seen.append((module, len(inputs)))
        if len(seen) == 2:
            raise _Cancelled()

    handle = layer.register_forward_pre_hook(hook)
    layer(torch.zeros(1, 4))
    with pytest.raises(_Cancelled):
        layer(torch.zeros(1, 4))
    handle.remove()
    layer(torch.zeros(1, 4))

    assert seen == [(layer, 1), (layer, 1)]


def test_grad_switches_behave_the_same():
    layer = torch.nn.Linear(2, 2)
    previous = torch.is_grad_enabled()
    torch.set_grad_enabled(False)  # forma usata da demucs4 (globale)
    try:
        assert not layer(torch.ones(1, 2)).requires_grad
    finally:
        torch.set_grad_enabled(previous)
    with torch.inference_mode():
        out = layer(torch.ones(1, 2))
    assert not out.requires_grad and out.is_inference()
    assert torch.is_grad_enabled() == previous


def test_mps_probe_is_safe_everywhere():
    # device.py interroga torch.backends.mps anche su Windows e Linux
    backend = getattr(torch.backends, "mps", None)
    assert backend is not None
    assert isinstance(backend.is_available(), bool)
    assert isinstance(backend.is_built(), bool)
    assert isinstance(torch.cuda.is_available(), bool)


def test_from_numpy_roundtrip_with_this_numpy():
    audio = np.arange(12, dtype=np.float32).reshape(2, 6)
    block = np.ascontiguousarray(audio[:, 1:5])  # come pipeline.py

    tensor = torch.from_numpy(block)
    tensor[0, 0] = 99.0  # condivide la memoria: nessuna copia nascosta

    assert block[0, 0] == 99.0
    assert tensor.dtype == torch.float32
    back = (tensor * 2).numpy()
    assert back.dtype == np.float32 and back.shape == (2, 4)


def test_std_is_unbiased_like_demucs_expects():
    # demucs4 normalizza con ref.std(): correzione di Bessel in entrambe
    values = np.array([1.0, 2.0, 4.0, 7.0], dtype=np.float32)
    assert float(torch.from_numpy(values).std()) == pytest.approx(np.std(values, ddof=1), rel=1e-6)


def test_hub_api_used_by_demucs(tmp_path):
    previous = torch.hub.get_dir()
    torch.hub.set_dir(str(tmp_path))
    try:
        assert torch.hub.get_dir() == str(tmp_path)
    finally:
        torch.hub.set_dir(previous)
    load = inspect.signature(torch.hub.load_state_dict_from_url).parameters
    # demucs passa check_hash=True; weights_only resta False in ENTRAMBE:
    # il percorso remoto di demucs fa il pickle completo, per questo
    # i pesi si caricano con compat.load_checkpoint
    assert "check_hash" in load and load["weights_only"].default is False
    assert "hash_prefix" in inspect.signature(torch.hub.download_url_to_file).parameters


def test_torch_load_default_is_the_difference_compat_handles():
    default = inspect.signature(torch.load).parameters["weights_only"].default
    if compat.torch_version() < (2, 6):
        assert default is False
    else:
        assert default in (None, True)  # None = True salvo variabili d'ambiente
    assert compat.has_weights_only_allowlist() == (compat.torch_version() >= (2, 5))
