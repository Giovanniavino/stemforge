"""Decodifica (§5.7 regola 1, D9) con un FFmpeg finto al posto di quello dell'app.

Il modulo vero (engine/ffmpeg.py) chiama un binario LGPL compilato in
CI; qui si verifica come il motore lo USA, iniettando un modulo finto
in sys.modules con lo stesso contratto: locate, decode, probe_duration,
FfmpegMissing, DecodeError.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from stemforge.engine import audio_io, decode
from stemforge.engine.errors import NonFiniteAudioError, TooLongError, UnsupportedFormatError

FFMPEG = "stemforge.engine.ffmpeg"


class FakeFfmpeg(types.ModuleType):
    """Stesso contratto di engine/ffmpeg.py, senza processi."""

    class FfmpegMissing(RuntimeError):
        pass

    class DecodeError(ValueError):
        pass

    def __init__(self, audio=None, samplerate=44100, error=None, duration=None):
        super().__init__(FFMPEG)
        self.audio, self.samplerate, self.error, self.duration = audio, samplerate, error, duration
        self.decoded: list[Path] = []

    def locate(self):
        return None if isinstance(self.error, self.FfmpegMissing) else Path("ffmpeg")

    def decode(self, path):
        self.decoded.append(Path(path))
        if self.error is not None:
            raise self.error
        return self.audio, self.samplerate

    def probe_duration(self, path):
        if self.error is not None:
            raise self.error
        if self.duration is not None:
            return self.duration
        return None if self.audio is None else len(self.audio) / self.samplerate


@pytest.fixture()
def fake_ffmpeg(monkeypatch):
    def install(**kwargs) -> FakeFfmpeg:
        fake = FakeFfmpeg(**kwargs)
        monkeypatch.setitem(sys.modules, FFMPEG, fake)
        return fake

    return install


def _container(tmp_path: Path, name: str = "brano.m4a") -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64)  # non è roba di libsndfile
    return path


def _tone(frames: int, channels: int) -> np.ndarray:
    t = np.arange(frames) / 44100
    return np.stack([0.1 * (c + 1) * np.sin(2 * np.pi * 220 * t) for c in range(channels)], axis=1)


def test_m4a_goes_to_the_app_ffmpeg_with_all_channels(tmp_path, fake_ffmpeg):
    fake = fake_ffmpeg(audio=_tone(48000, 6).astype(np.float32), samplerate=48000)
    source = audio_io.load(_container(tmp_path))
    assert fake.decoded, "m4a deve passare dal FFmpeg dell'app"
    assert source.samplerate == 48000 and source.original_frames == 48000
    assert source.source_channels == 6 and source.downmixed
    assert source.data.shape == (2, 48000)


def test_soundfile_formats_never_touch_ffmpeg(tmp_path, fake_ffmpeg):
    fake = fake_ffmpeg(error=AssertionError("non doveva essere chiamato"))
    path = tmp_path / "a.wav"
    sf.write(path, _tone(4410, 2), 44100, subtype="PCM_24")
    assert audio_io.load(path).original_frames == 4410
    assert not fake.decoded


@pytest.mark.parametrize(
    ("name", "error", "key"),
    [
        ("brano.m4a", "missing", "err.ffmpeg_missing"),
        ("brano.m4a", "DRM", "err.drm"),
        ("brano.m4a", "corrupt", "err.corrupt"),
        ("brano.wav", "corrupt", "err.corrupt"),  # wav rotto: libsndfile e FFmpeg d'accordo
        ("brano.wav", "missing", "err.corrupt"),  # libsndfile doveva bastare: è il file
        ("brano.xyz", "corrupt", "err.unsupported"),
        ("brano.xyz", "missing", "err.unsupported"),
    ],
)
def test_decoder_failures_become_actionable_errors(tmp_path, fake_ffmpeg, name, error, key):
    fake = FakeFfmpeg()
    exc = {
        "missing": fake.FfmpegMissing("FFmpeg dell'app non trovato"),
        "DRM": fake.DecodeError("brano.m4p è protetto da DRM"),
        "corrupt": fake.DecodeError("Invalid data found when processing input"),
    }[error]
    fake_ffmpeg(error=exc)
    with pytest.raises(UnsupportedFormatError) as info:
        audio_io.load(_container(tmp_path, name))
    assert info.value.key == key
    assert info.value.params["name"] == name


def test_without_the_ffmpeg_module_m4a_says_what_to_do(tmp_path, monkeypatch):
    # None in sys.modules fa fallire l'import: il modulo dell'app non c'è
    monkeypatch.setitem(sys.modules, FFMPEG, None)
    with pytest.raises(UnsupportedFormatError) as info:
        audio_io.load(_container(tmp_path))
    assert info.value.key == "err.ffmpeg_missing"
    assert decode.probe_duration(_container(tmp_path)) is None


def test_never_falls_back_to_a_system_ffmpeg(tmp_path, monkeypatch):
    # D9: un ffmpeg nel PATH (magari GPL) non deve mai entrare nell'app
    monkeypatch.setitem(sys.modules, FFMPEG, None)
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError(f"processo esterno lanciato: {args}")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(UnsupportedFormatError):
        audio_io.load(_container(tmp_path))


def test_too_long_is_refused_before_decoding(tmp_path, fake_ffmpeg):
    fake = fake_ffmpeg(audio=_tone(10, 2).astype(np.float32), duration=31 * 60.0)
    with pytest.raises(TooLongError) as info:
        audio_io.load(_container(tmp_path))
    assert not fake.decoded, "30+ minuti non si decodificano per niente"
    assert info.value.params["minutes"] == 31


def test_too_long_is_refused_even_if_the_header_lies(tmp_path, fake_ffmpeg):
    frames = int((audio_io.MAX_DURATION_S + 1) * 8000)
    fake_ffmpeg(audio=np.zeros((frames, 1), np.float32), samplerate=8000, duration=60.0)
    with pytest.raises(TooLongError):
        audio_io.load(_container(tmp_path))


def test_exactly_thirty_minutes_is_accepted(tmp_path, fake_ffmpeg):
    frames = audio_io.MAX_DURATION_S * 8000
    fake_ffmpeg(audio=np.zeros((frames, 1), np.float32), samplerate=8000)
    assert audio_io.load(_container(tmp_path)).duration_s == audio_io.MAX_DURATION_S


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_samples_are_refused(tmp_path, bad):
    audio = _tone(4410, 2).astype(np.float32)
    audio[1234, 1] = bad
    path = tmp_path / "nan.wav"
    sf.write(path, audio, 44100, subtype="FLOAT")
    with pytest.raises(NonFiniteAudioError) as info:
        audio_io.load(path)
    assert info.value.key == "err.non_finite"


def test_float_clipping_is_kept_not_refused(tmp_path):
    # §5.7 regola 8: oltre 0 dBFS nei float si conserva
    audio = _tone(4410, 2).astype(np.float32) * 20.0
    path = tmp_path / "hot.wav"
    sf.write(path, audio, 44100, subtype="FLOAT")
    assert float(np.max(np.abs(audio_io.load(path).data))) > 1.5


def test_empty_file_says_so(tmp_path):
    path = tmp_path / "vuoto.wav"
    sf.write(path, np.zeros((0, 2), np.float32), 44100, subtype="PCM_16")
    with pytest.raises(UnsupportedFormatError) as info:
        audio_io.load(path)
    assert info.value.key == "err.empty"


def test_more_than_eight_channels_is_refused_clearly(tmp_path):
    path = tmp_path / "16ch.wav"
    sf.write(path, _tone(441, 16), 44100, subtype="PCM_16")
    with pytest.raises(UnsupportedFormatError) as info:
        audio_io.load(path)
    assert info.value.key == "err.channels" and info.value.params["channels"] == 16


def test_missing_file(tmp_path):
    with pytest.raises(UnsupportedFormatError) as info:
        audio_io.load(tmp_path / "manca.wav")
    assert info.value.key == "err.not_found"


def test_probe_duration_uses_ffmpeg_only_where_soundfile_cannot(tmp_path, fake_ffmpeg):
    fake_ffmpeg(duration=12.5)
    assert decode.probe_duration(_container(tmp_path)) == 12.5
    fake_ffmpeg(error=FakeFfmpeg.DecodeError("rotto"))
    assert decode.probe_duration(_container(tmp_path)) is None


def test_the_drop_list_does_not_load_the_decoders():
    # §8.5: l'UI importa worker/planning per rifiutare al drop, e quel
    # processo non deve caricare libsndfile (né torch) per una lista di estensioni
    import subprocess

    code = (
        "import sys, stemforge.worker.planning as p;"
        "print(sorted(m for m in ('soundfile', 'torch') if m in sys.modules));"
        "print(p.SUPPORTED_SUFFIXES == __import__('stemforge.engine.decode',"
        " fromlist=['x']).SUPPORTED_EXTENSIONS)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["[]", "True"], out.stdout + out.stderr


def test_supported_extensions_cover_the_spec():
    # §5.7: wav flac mp3 ogg aiff m4a/aac alac (alac sta in .m4a)
    for ext in (".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif", ".m4a", ".aac"):
        assert ext in decode.SUPPORTED_EXTENSIONS
