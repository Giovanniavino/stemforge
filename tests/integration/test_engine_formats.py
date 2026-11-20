"""Formati, sample rate e canali (§5.7) con l'invariante di §10.2 per ognuno.

Per ogni formato valido: il file si carica a float32 col sample rate
originale, gli stem tornano alla stessa lunghezza in campioni e allo
stesso sample rate, e la loro somma ricostruisce il mix decodificato
(< -40 dBFS). I fixture si generano in codice; i formati compressi che
solo FFmpeg sa scrivere passano da encode_fixture del FFmpeg dell'app,
con skip pulito se qui non è compilato (in CI c'è).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from stemforge.engine import audio_io, downmix
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K
from stemforge.worker.pipeline import run_job

from tests.integration.conftest import collect_messages

LIMIT_DBFS = -40.0
SECONDS = 1.0

LOSSLESS = [
    ("wav", "PCM_16"), ("wav", "PCM_24"), ("wav", "PCM_32"), ("wav", "FLOAT"), ("wav", "DOUBLE"),
    ("flac", "PCM_16"), ("flac", "PCM_24"), ("aiff", "PCM_16"), ("aiff", "PCM_24"),
]
LOSSY = [("ogg", "VORBIS"), ("mp3", "MPEG_LAYER_III")]
RATES = [8000, 22050, 44100, 48000, 88200, 96000, 192000]
# quantizzazione del formato di partenza: il caricamento non deve aggiungere altro
QUANT = {"PCM_16": 2.0 / 32768, "PCM_24": 2.0 / 2**23, "PCM_32": 1e-6, "FLOAT": 0.0, "DOUBLE": 0.0}


def multichannel(samplerate: int, channels: int, seconds: float = SECONDS) -> np.ndarray:
    """[channels, frames]: un tono diverso per canale, così ogni canale si riconosce."""
    t = np.arange(int(seconds * samplerate)) / samplerate
    rng = np.random.default_rng(seed=channels)
    rows = [
        0.12 * np.sin(2 * np.pi * (110.0 * (c + 1)) * t) + 0.01 * rng.standard_normal(t.size)
        for c in range(channels)
    ]
    return np.stack(rows).astype(np.float32)


def write(path: Path, audio: np.ndarray, samplerate: int, subtype: str) -> Path:
    sf.write(path, audio.T, samplerate, subtype=subtype)
    return path


def _job(source: Path, out: Path) -> SeparationJob:
    return SeparationJob(
        source=source, wanted=(K.VOCALS, K.DRUMS, K.BASS, K.OTHER), quality="balanced",
        out_dir=out, fmt="wav", device="cpu",
    )


def _run(source: Path, tmp_path: Path, fake_backends):
    cache, _fake = fake_backends()
    messages, emit = collect_messages()
    return run_job(_job(source, tmp_path / "out"), emit, backends=cache), messages


def assert_invariant(out_dir: Path, source: Path) -> None:
    """Stem: stesso sample rate, stessa lunghezza, somma = mix decodificato."""
    loaded = audio_io.load(source)
    mix = audio_io.to_original_channels(loaded.data, loaded.original_channels).T.astype(np.float64)
    total = np.zeros_like(mix)
    for stem in sorted(out_dir.glob("*.wav")):
        data, rate = sf.read(stem, dtype="float64", always_2d=True)
        assert rate == loaded.samplerate, f"{stem.name}: {rate} Hz invece di {loaded.samplerate}"
        assert data.shape == mix.shape, f"{stem.name}: {data.shape} invece di {mix.shape}"
        total += data
    rms = float(np.sqrt(np.mean(np.square(total - mix))))
    residual = -120.0 if rms == 0 else 20.0 * math.log10(rms)
    assert residual < LIMIT_DBFS, f"ricostruzione a {residual:.1f} dBFS"


# -- caricamento: tutta la matrice, senza torch -------------------------------


@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize(("fmt", "subtype"), LOSSLESS, ids=lambda v: str(v))
@pytest.mark.parametrize("channels", [1, 2, 6])
def test_lossless_loads_exactly(tmp_path, fmt, subtype, rate, channels):
    audio = multichannel(rate, channels)
    path = write(tmp_path / f"x.{fmt}", audio, rate, subtype)
    source = audio_io.load(path)
    assert source.data.dtype == np.float32 and source.data.shape[0] == 2
    assert source.samplerate == rate
    assert source.original_frames == audio.shape[1], "neanche un campione di scarto"
    assert source.original_channels == (1 if channels == 1 else 2)
    if channels == 1:
        expected = np.repeat(audio, 2, axis=0)  # regola 3: duplicato per il modello
    elif channels == 2:
        expected = audio
    else:
        expected = downmix.matrix(channels) @ audio.astype(np.float64)  # regola 7
    np.testing.assert_allclose(source.data, expected, atol=QUANT[subtype] * 3 + 1e-6)


# Le frequenze che ogni codec sa scrivere: MPEG-1/2/2.5 layer III arriva
# a 48 kHz, Vorbis copre tutta la gamma di §5.7.
LOSSY_RATES = [(fmt, subtype, rate) for fmt, subtype in LOSSY for rate in RATES
               if fmt != "mp3" or rate <= 48000]


@pytest.mark.parametrize(("fmt", "subtype", "rate"), LOSSY_RATES, ids=lambda v: str(v))
def test_lossy_loads_at_original_rate_and_reconstructs(tmp_path, fake_backends, fmt, subtype,
                                                       rate):
    path = write(tmp_path / f"brano.{fmt}", multichannel(rate, 2), rate, subtype)
    source = audio_io.load(path)
    assert source.samplerate == rate
    assert abs(source.duration_s - SECONDS) < 0.1  # ritardo del codec, mai 100 ms
    assert float(np.max(np.abs(source.data))) > 0.05
    result, _ = _run(path, tmp_path, fake_backends)
    assert_invariant(result.out_dir, path)


# -- invariante e lunghezza attraverso la pipeline ----------------------------


@pytest.mark.parametrize(("fmt", "subtype"), LOSSLESS + LOSSY, ids=lambda v: str(v))
def test_every_format_reconstructs(tmp_path, fake_backends, fmt, subtype):
    source = write(tmp_path / f"brano.{fmt}", multichannel(44100, 2), 44100, subtype)
    result, _ = _run(source, tmp_path, fake_backends)
    assert_invariant(result.out_dir, source)


@pytest.mark.parametrize("rate", RATES)
def test_every_samplerate_round_trips_to_the_sample(tmp_path, fake_backends, rate):
    # regola 2: resampling a 44.1k e ritorno, lunghezza imposta al campione
    source = write(tmp_path / "brano.wav", multichannel(rate, 2), rate, "PCM_24")
    result, _ = _run(source, tmp_path, fake_backends)
    assert sf.info(str(result.out_dir / "vocals.wav")).frames == sf.info(str(source)).frames
    assert_invariant(result.out_dir, source)


@pytest.mark.parametrize("rate", [22050, 48000])
@pytest.mark.parametrize("channels", [1, 3, 4, 5, 6, 7, 8])
def test_every_channel_layout_reconstructs(tmp_path, fake_backends, channels, rate):
    source = write(tmp_path / "brano.wav", multichannel(rate, channels), rate, "PCM_24")
    result, _ = _run(source, tmp_path, fake_backends)
    stem_channels = sf.info(str(result.out_dir / "vocals.wav")).channels
    assert stem_channels == (1 if channels == 1 else 2)
    assert_invariant(result.out_dir, source)
    downmix_warnings = [w for w in result.warnings if "BS.775" in w]
    assert bool(downmix_warnings) == (channels > 2), "il downmix si dichiara, sempre e solo lui"


def test_51_keeps_the_centre_where_the_voice_is(tmp_path, fake_backends):
    # regola 7: con i primi due canali la voce (nel centro) sparirebbe
    rate = 44100
    audio = np.zeros((6, rate), np.float32)
    audio[2] = 0.5 * np.sin(2 * np.pi * 440.0 * np.arange(rate) / rate)  # solo C
    audio[3] = 0.9  # LFE costante: escluso dal downmix
    source = write(tmp_path / "film.wav", audio, rate, "FLOAT")
    result, messages = _run(source, tmp_path, fake_backends)
    vocals, _ = sf.read(result.out_dir / "vocals.wav", always_2d=True)
    loaded = audio_io.load(source)
    np.testing.assert_allclose(loaded.data[0], audio[2] * downmix.MINUS_3_DB, atol=1e-6)
    np.testing.assert_allclose(loaded.data[0], loaded.data[1], atol=1e-7)
    assert float(np.max(np.abs(vocals))) > 0.05, "la voce del centro è negli stem"
    assert abs(float(np.mean(loaded.data))) < 1e-3, "LFE escluso"
    warnings = [m.message for m in messages if type(m).__name__ == "Warning_"]
    assert any("6" in w and "BS.775" in w for w in warnings)


def test_bs775_coefficients():
    m = downmix.matrix(6)  # L R C LFE Ls Rs
    g = math.sqrt(0.5)
    np.testing.assert_allclose(m, [[1, 0, g, 0, g, 0], [0, 1, g, 0, 0, g]])
    assert not np.any(downmix.matrix(8)[:, 3]), "LFE escluso anche nel 7.1"


def test_non_finite_file_never_reaches_the_model(tmp_path, fake_backends):
    audio = multichannel(44100, 2)
    audio[0, 100] = np.nan
    source = write(tmp_path / "nan.wav", audio, 44100, "FLOAT")
    cache, fake = fake_backends()
    with pytest.raises(audio_io.NonFiniteAudioError):
        run_job(_job(source, tmp_path / "out"), lambda m: None, backends=cache)
    assert not fake.calls
    assert not (tmp_path / "out").exists(), "niente cartella per un file rifiutato"


# -- formati che solo il FFmpeg dell'app sa scrivere --------------------------


def _app_ffmpeg():
    ffmpeg = pytest.importorskip("stemforge.engine.ffmpeg")
    if ffmpeg.locate() is None:
        pytest.skip("FFmpeg dell'app non compilato su questa macchina (in CI c'è)")
    return ffmpeg


# L'encoder AAC di FFmpeg arriva a 96 kHz; ALAC copre tutta la gamma di §5.7.
FFMPEG_CASES = (
    [("aac", "brano.m4a", False, rate) for rate in RATES if rate <= 96000]
    + [("alac", "brano.m4a", True, rate) for rate in RATES]
)


@pytest.mark.parametrize(("codec", "name", "lossless", "rate"), FFMPEG_CASES, ids=lambda v: str(v))
def test_ffmpeg_formats_reconstruct(tmp_path, fake_backends, codec, name, lossless, rate):
    ffmpeg = _app_ffmpeg()
    audio = multichannel(rate, 2)
    source = ffmpeg.encode_fixture(audio, rate, tmp_path / name, codec)
    loaded = audio_io.load(source)
    assert loaded.samplerate == rate
    if lossless:
        assert loaded.original_frames == audio.shape[1]
        np.testing.assert_allclose(loaded.data, audio, atol=2.0 / 32768)
    result, _ = _run(source, tmp_path, fake_backends)
    assert_invariant(result.out_dir, source)


def test_ffmpeg_multichannel_is_downmixed(tmp_path, fake_backends):
    ffmpeg = _app_ffmpeg()
    audio = multichannel(48000, 6)
    source = ffmpeg.encode_fixture(audio, 48000, tmp_path / "film.m4a", "alac")
    loaded = audio_io.load(source)
    assert loaded.source_channels == 6 and loaded.downmixed
    result, _ = _run(source, tmp_path, fake_backends)
    assert_invariant(result.out_dir, source)
