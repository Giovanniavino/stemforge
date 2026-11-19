"""Il FFmpeg LGPL vero sui contenitori che lui stesso non sa scrivere (D9).

La build minima ha i demuxer aiff/w64/caf/ogg/mp3 ma non i muxer: i
fixture li scrive libsndfile (soundfile, gia' dipendenza del progetto),
in codice. Per i formati senza perdita il riferimento e' la lettura di
soundfile dello stesso file: le due strade devono dare gli stessi float.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from stemforge.engine import ffmpeg

pytestmark = pytest.mark.skipif(
    ffmpeg.locate() is None,
    reason="FFmpeg LGPL di sviluppo assente: packaging/ffmpeg/build.sh <profilo> "
    f"oppure {ffmpeg.ENV_VAR}=<percorso di ffmpeg>",
)

SECONDS = 1.5
AMPLITUDE = 0.5
CHANNEL_HZ = (220.0, 440.0, 660.0, 110.0, 880.0, 1100.0, 1320.0, 1540.0)
# interi a 16/24 bit e float32 diventano float32 senza arrotondamenti in
# entrambe le strade: l'unica differenza ammessa e' l'ultimo bit
EXACT_TOL = 1e-7
# ritardo e riempimento degli encoder con perdita (Vorbis, Opus, MP3 di
# LAME): FFmpeg li toglie dove il file li dichiara, non sempre al campione
LOSSY_LENGTH_SLACK = 4096
PITCH_TOL_HZ = 4.0


def tones(samplerate: int, channels: int) -> np.ndarray:
    """[frames, channels] per soundfile: canale k = sinusoide a CHANNEL_HZ[k]."""
    t = np.arange(int(samplerate * SECONDS)) / samplerate
    cols = [AMPLITUDE * np.sin(2 * np.pi * CHANNEL_HZ[k] * t) for k in range(channels)]
    return np.stack(cols, axis=1).astype(np.float32)


def dominant_hz(signal: np.ndarray, samplerate: int) -> float:
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    return float(np.argmax(spectrum)) * samplerate / len(signal)


LOSSLESS = [
    ("WAV", "FLOAT", ".wav"),
    ("WAV", "PCM_24", ".wav"),
    ("WAVEX", "PCM_16", ".wav"),
    ("AIFF", "PCM_24", ".aiff"),  # big-endian: pcm_s24be
    ("AIFF", "PCM_16", ".aif"),
    ("W64", "FLOAT", ".w64"),
    ("CAF", "PCM_24", ".caf"),
    ("FLAC", "PCM_24", ".flac"),
]


@pytest.mark.parametrize(("fmt", "subtype", "ext"), LOSSLESS)
def test_lossless_containers_match_soundfile(tmp_path, fmt, subtype, ext):
    path = tmp_path / f"t{ext}"
    sf.write(path, tones(48000, 2), 48000, format=fmt, subtype=subtype)
    reference, ref_rate = sf.read(path, dtype="float32", always_2d=True)
    decoded, rate = ffmpeg.decode(path)
    assert (rate, decoded.dtype) == (ref_rate, np.float32)
    assert decoded.shape == reference.shape
    assert np.max(np.abs(decoded - reference)) <= EXACT_TOL


@pytest.mark.parametrize("samplerate", [8000, 192000])
def test_wav_7_1_float_at_extreme_rates(tmp_path, samplerate):
    path = tmp_path / "surround.wav"
    source = tones(samplerate, 8)
    sf.write(path, source, samplerate, format="WAV", subtype="FLOAT")
    decoded, rate = ffmpeg.decode(path)
    assert rate == samplerate and decoded.shape == source.shape
    assert np.array_equal(decoded, source)
    assert ffmpeg.probe_duration(path) == pytest.approx(SECONDS, abs=0.01)


LOSSY = [
    ("OGG", "VORBIS", ".ogg", 44100),
    ("OGG", "OPUS", ".opus", 48000),
    ("MP3", "MPEG_LAYER_III", ".mp3", 44100),
]


@pytest.mark.parametrize(("fmt", "subtype", "ext", "samplerate"), LOSSY)
def test_lossy_containers_keep_rate_length_and_pitch(tmp_path, fmt, subtype, ext,
                                                     samplerate):
    path = tmp_path / f"t{ext}"
    source = tones(samplerate, 2)
    sf.write(path, source, samplerate, format=fmt, subtype=subtype)
    decoded, rate = ffmpeg.decode(path)
    assert rate == samplerate and decoded.shape[1] == 2
    assert abs(decoded.shape[0] - source.shape[0]) <= LOSSY_LENGTH_SLACK
    middle = decoded[samplerate // 4 : samplerate, :]
    for channel in range(2):
        assert dominant_hz(middle[:, channel], samplerate) == pytest.approx(
            CHANNEL_HZ[channel], abs=PITCH_TOL_HZ)
    assert ffmpeg.probe_duration(path) == pytest.approx(SECONDS, abs=0.1)


def test_decoded_array_is_writable_and_contiguous(tmp_path):
    # audio_io fa downmix e resampling sul posto: niente viste in sola lettura
    path = tmp_path / "w.wav"
    sf.write(path, tones(44100, 2), 44100, subtype="PCM_24")
    decoded, _ = ffmpeg.decode(path)
    assert decoded.flags.writeable and decoded.flags.c_contiguous
    decoded *= 0.5


def test_probe_duration_of_non_audio_and_missing(tmp_path):
    picture = tmp_path / "copertina.jpg"
    picture.write_bytes(b"\xff\xd8\xff\xe0" + bytes(2000))
    assert ffmpeg.probe_duration(picture) is None
    assert ffmpeg.probe_duration(Path(tmp_path / "sparito.m4a")) is None
