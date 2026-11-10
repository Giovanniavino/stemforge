"""Il FFmpeg LGPL vero davanti a file sbagliati (§5.7.1, §10.1).

Corrotto, vuoto, non audio, protetto da DRM: sempre DecodeError con un
messaggio per l'utente, mai un crash né un array vuoto o di forma strana.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from stemforge.engine import ffmpeg

pytestmark = pytest.mark.skipif(
    ffmpeg.locate() is None,
    reason="FFmpeg LGPL di sviluppo assente: packaging/ffmpeg/build.sh <profilo> "
    f"oppure {ffmpeg.ENV_VAR}=<percorso di ffmpeg>",
)

SAMPLERATE = 44100


def _aac_m4a(tmp_path: Path, name: str = "ok.m4a") -> Path:
    t = np.arange(SAMPLERATE) / SAMPLERATE
    audio = np.stack([0.4 * np.sin(2 * np.pi * 440.0 * t)] * 2).astype(np.float32)
    return ffmpeg.encode_fixture(audio, SAMPLERATE, tmp_path / name, "aac")


def _decode_error(path: Path) -> str:
    with pytest.raises(ffmpeg.DecodeError) as caught:
        ffmpeg.decode(path)
    message = str(caught.value)
    assert path.name in message
    return message


def test_empty_file(tmp_path):
    empty = tmp_path / "vuoto.m4a"
    empty.write_bytes(b"")
    _decode_error(empty)
    assert ffmpeg.probe_duration(empty) is None


def test_text_file_is_not_audio(tmp_path):
    text = tmp_path / "appunti.mp3"
    text.write_text("non sono una canzone\n" * 200, encoding="utf-8")
    assert "non è un file audio" in _decode_error(text)
    assert ffmpeg.probe_duration(text) is None


def test_random_bytes(tmp_path):
    noise = tmp_path / "rumore.m4a"
    noise.write_bytes(np.random.default_rng(7).integers(0, 256, 50_000, np.uint8).tobytes())
    _decode_error(noise)


def test_truncated_m4a(tmp_path):
    # il moov di un m4a scritto da ffmpeg sta in fondo: troncato a metà
    # il file non ha più l'indice dei campioni
    good = _aac_m4a(tmp_path)
    cut = tmp_path / "troncato.m4a"
    cut.write_bytes(good.read_bytes()[: good.stat().st_size // 2])
    _decode_error(cut)


def test_drm_protected_m4a_says_drm(tmp_path):
    # un acquisto iTunes FairPlay (.m4p) ha la voce "drms" al posto di
    # "mp4a" nella descrizione dei campioni: la si riproduce cambiando
    # solo quei quattro byte di un m4a generato qui
    data = bytearray(_aac_m4a(tmp_path).read_bytes())
    entry = data.find(b"mp4a")
    assert entry > 0
    data[entry : entry + 4] = b"drms"
    protected = tmp_path / "acquisto.m4p"
    protected.write_bytes(bytes(data))
    assert "DRM" in _decode_error(protected)


def test_missing_file_and_folder(tmp_path):
    assert "non esiste" in _decode_error(tmp_path / "sparito.flac")
    folder = tmp_path / "cartella.wav"
    folder.mkdir()
    _decode_error(folder)


@pytest.mark.skipif(sys.platform == "win32", reason="':' non ammesso nei nomi Windows")
def test_name_that_looks_like_a_protocol_is_a_file(tmp_path, monkeypatch):
    # "pipe:1" come nome di file non deve diventare lo stdout di ffmpeg
    monkeypatch.chdir(tmp_path)
    _aac_m4a(tmp_path, "pipe:1.m4a")
    decoded, rate = ffmpeg.decode(Path("pipe:1.m4a"))
    assert rate == SAMPLERATE and decoded.shape[1] == 2
