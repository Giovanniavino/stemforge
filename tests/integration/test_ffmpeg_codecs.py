"""Il FFmpeg LGPL vero (D9): codifica e decodifica dei formati che contano.

Si saltano se il binario di sviluppo manca (packaging/ffmpeg/build.sh o
STEMFORGE_FFMPEG); in CI il binario c'è sempre. Ogni fixture nasce qui,
in codice: sinusoidi a frequenze diverse per canale, così l'ordine dei
canali e il sample rate si verificano dallo spettro, non dalla forma.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from stemforge.engine import ffmpeg

pytestmark = pytest.mark.skipif(
    ffmpeg.locate() is None,
    reason="FFmpeg LGPL di sviluppo assente: packaging/ffmpeg/build.sh <profilo> "
    f"oppure {ffmpeg.ENV_VAR}=<percorso di ffmpeg>",
)

SECONDS = 1.5
AMPLITUDE = 0.5
# errore massimo di un passaggio intero: 16 bit, 24 bit (flac, alac, s24)
TOL_16 = 2.0 / 2**15
TOL_24 = 2.0 / 2**23
# l'encoder AAC aggiunge priming e riempie l'ultimo frame da 1024 campioni:
# le edit list di mov lo tolgono, ma non sempre al campione
AAC_LENGTH_SLACK = 2048


# una frequenza diversa per canale; il quarto e' l'LFE del 5.1, che
# l'encoder AAC taglia sopra ~120 Hz: li' serve una nota grave
CHANNEL_HZ = (220.0, 440.0, 660.0, 110.0, 880.0, 1100.0)


def tones(samplerate: int, channels: int, seconds: float = SECONDS) -> np.ndarray:
    """[channels, frames]: canale k = sinusoide a CHANNEL_HZ[k]."""
    t = np.arange(int(samplerate * seconds)) / samplerate
    rows = [AMPLITUDE * np.sin(2 * np.pi * CHANNEL_HZ[k] * t) for k in range(channels)]
    return np.stack(rows).astype(np.float32)


def dominant_hz(signal: np.ndarray, samplerate: int) -> float:
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return float(np.argmax(spectrum)) * samplerate / len(signal)


def roundtrip(tmp_path: Path, codec: str, ext: str, samplerate: int,
              channels: int) -> tuple[np.ndarray, np.ndarray, int]:
    source = tones(samplerate, channels)
    dest = ffmpeg.encode_fixture(source, samplerate, tmp_path / f"t{ext}", codec)
    decoded, rate = ffmpeg.decode(dest)
    assert decoded.dtype == np.float32 and decoded.ndim == 2
    return source, decoded, rate


LOSSLESS = [
    ("flac", ".flac", TOL_24),
    ("alac", ".m4a", TOL_24),
    ("pcm_s24le", ".wav", TOL_24),
    ("pcm_s16le", ".wav", TOL_16),
]


@pytest.mark.parametrize(("codec", "ext", "tol"), LOSSLESS)
@pytest.mark.parametrize("samplerate", [8000, 22050, 44100, 48000, 96000, 192000])
def test_lossless_roundtrip_is_sample_exact(tmp_path, codec, ext, tol, samplerate):
    source, decoded, rate = roundtrip(tmp_path, codec, ext, samplerate, 2)
    assert rate == samplerate
    assert decoded.shape == (source.shape[1], 2)
    assert np.max(np.abs(decoded - source.T)) <= tol


def test_alac_in_caf_container(tmp_path):
    source, decoded, rate = roundtrip(tmp_path, "alac", ".caf", 44100, 2)
    assert rate == 44100 and decoded.shape == source.T.shape
    assert np.max(np.abs(decoded - source.T)) <= TOL_24


@pytest.mark.parametrize("samplerate", [8000, 22050, 44100, 48000, 96000])
def test_aac_keeps_rate_length_and_pitch(tmp_path, samplerate):
    source, decoded, rate = roundtrip(tmp_path, "aac", ".m4a", samplerate, 2)
    assert rate == samplerate and decoded.shape[1] == 2
    assert abs(decoded.shape[0] - source.shape[1]) <= AAC_LENGTH_SLACK
    middle = decoded[samplerate // 4 : samplerate, :]
    for channel in range(2):
        assert dominant_hz(middle[:, channel], samplerate) == pytest.approx(
            CHANNEL_HZ[channel], abs=4.0)


@pytest.mark.parametrize(("codec", "ext"), [("flac", ".flac"), ("alac", ".m4a"),
                                            ("pcm_s24le", ".wav"), ("aac", ".m4a")])
def test_multichannel_keeps_every_channel_in_order(tmp_path, codec, ext):
    # 5.1: tutti i canali tornano, ognuno con la sua frequenza (il downmix
    # ITU lo fa audio_io; qui perdere o scambiare un canale sarebbe un bug)
    samplerate = 48000
    source, decoded, rate = roundtrip(tmp_path, codec, ext, samplerate, 6)
    assert rate == samplerate and decoded.shape[1] == 6
    middle = decoded[samplerate // 4 : samplerate, :]
    found = [dominant_hz(middle[:, k], samplerate) for k in range(6)]
    assert found == pytest.approx(list(CHANNEL_HZ), abs=4.0)


def test_mono_stays_mono(tmp_path):
    source, decoded, _ = roundtrip(tmp_path, "flac", ".flac", 44100, 1)
    assert decoded.shape == (source.shape[1], 1)


def test_probe_duration(tmp_path):
    dest = ffmpeg.encode_fixture(tones(48000, 2, 3.0), 48000, tmp_path / "d.flac", "flac")
    assert ffmpeg.probe_duration(dest) == pytest.approx(3.0, abs=0.02)
    m4a = ffmpeg.encode_fixture(tones(44100, 2, 3.0), 44100, tmp_path / "d.m4a", "aac")
    assert ffmpeg.probe_duration(m4a) == pytest.approx(3.0, abs=0.05)


def test_unicode_and_spaces_in_path(tmp_path):
    folder = tmp_path / "cartella con spazi è ü"
    folder.mkdir()
    dest = ffmpeg.encode_fixture(tones(44100, 2), 44100, folder / "brano à.m4a", "alac")
    decoded, rate = ffmpeg.decode(dest)
    assert rate == 44100 and decoded.shape[1] == 2
    assert ffmpeg.probe_duration(dest) == pytest.approx(SECONDS, abs=0.02)


def test_license_info_declares_lgpl_without_gpl_flags():
    info = ffmpeg.license_info()
    assert "license: LGPL version 2.1 or later" in info
    assert "configuration:" in info
    for flag in ("--enable-gpl", "--enable-nonfree", "--enable-version3"):
        assert flag not in info
