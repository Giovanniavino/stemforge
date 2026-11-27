"""Il demuxer matroska della build minima (D9) su un .mka scritto qui.

Né la build minima né libsndfile scrivono Matroska: il file lo compone
il test, elemento per elemento (EBML), con una traccia PCM 16 bit. È il
minimo che un muxer vero produce: intestazione, Info, Tracks, Cluster.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from stemforge.engine import ffmpeg

pytestmark = pytest.mark.skipif(
    ffmpeg.locate() is None,
    reason="FFmpeg LGPL di sviluppo assente: packaging/ffmpeg/build.sh <profilo> "
    f"oppure {ffmpeg.ENV_VAR}=<percorso di ffmpeg>",
)

SAMPLERATE = 48000
SECONDS = 1.5
CHANNEL_HZ = (330.0, 550.0)
BLOCK_FRAMES = 4800
# TimecodeScale di default di Matroska: un tick = 1 ms
TICK_NS = 1_000_000
MS_PER_S = 1000


def _element(element_id: int, payload: bytes) -> bytes:
    """ID + dimensione su 8 byte (0x01 + 7 byte big-endian) + contenuto."""
    ident = element_id.to_bytes((element_id.bit_length() + 7) // 8, "big")
    return ident + b"\x01" + len(payload).to_bytes(7, "big") + payload


def _uint(element_id: int, value: int) -> bytes:
    return _element(element_id, value.to_bytes(8, "big"))


def _float(element_id: int, value: float) -> bytes:
    return _element(element_id, struct.pack(">d", value))


def _header() -> bytes:
    return _element(0x1A45DFA3, b"".join([
        _uint(0x4286, 1), _uint(0x42F7, 1), _uint(0x42F2, 4), _uint(0x42F3, 8),
        _element(0x4282, b"matroska"), _uint(0x4287, 4), _uint(0x4285, 2),
    ]))


def _track(channels: int) -> bytes:
    audio = _float(0xB5, float(SAMPLERATE)) + _uint(0x9F, channels) + _uint(0x6264, 16)
    entry = b"".join([
        _uint(0xD7, 1), _uint(0x73C5, 1), _uint(0x83, 2),  # traccia 1, audio
        _element(0x86, b"A_PCM/INT/LIT"), _element(0xE1, audio),
    ])
    return _element(0x1654AE6B, _element(0xAE, entry))


def _cluster(pcm: np.ndarray) -> bytes:
    blocks = [_uint(0xE7, 0)]
    for start in range(0, len(pcm), BLOCK_FRAMES):
        timecode_ms = start * MS_PER_S // SAMPLERATE
        # SimpleBlock: traccia (vint 0x81), timecode relativo int16, keyframe
        head = b"\x81" + struct.pack(">hB", timecode_ms, 0x80)
        blocks.append(_element(0xA3, head + pcm[start : start + BLOCK_FRAMES].tobytes()))
    return _element(0x1F43B675, b"".join(blocks))


def write_mka(path: Path, pcm: np.ndarray) -> Path:
    """pcm: [frames, channels] int16."""
    duration_ms = len(pcm) * MS_PER_S / SAMPLERATE
    info = _element(0x1549A966, _uint(0x2AD7B1, TICK_NS) + _float(0x4489, duration_ms))
    segment = _element(0x18538067, info + _track(pcm.shape[1]) + _cluster(pcm))
    path.write_bytes(_header() + segment)
    return path


def _tones() -> np.ndarray:
    t = np.arange(int(SAMPLERATE * SECONDS)) / SAMPLERATE
    cols = [0.5 * np.sin(2 * np.pi * hz * t) for hz in CHANNEL_HZ]
    return np.round(np.stack(cols, axis=1) * 32767).astype("<i2")


def test_matroska_pcm_is_sample_exact(tmp_path):
    pcm = _tones()
    decoded, rate = ffmpeg.decode(write_mka(tmp_path / "brano.mka", pcm))
    assert rate == SAMPLERATE and decoded.shape == pcm.shape
    # pcm_s16le -> float: divisione esatta per 32768, nessun arrotondamento
    assert np.array_equal(decoded, pcm.astype(np.float32) / 32768)
    assert ffmpeg.probe_duration(tmp_path / "brano.mka") == pytest.approx(SECONDS, abs=0.01)


def test_matroska_truncated_is_a_decode_error_or_shorter(tmp_path):
    # un .mka troncato nel mezzo di un blocco: o errore per l'utente o i
    # campioni interi fino al taglio, mai un array di forma sbagliata
    whole = write_mka(tmp_path / "intero.mka", _tones()).read_bytes()
    cut = tmp_path / "troncato.mka"
    cut.write_bytes(whole[: len(whole) // 2 + 1])
    try:
        decoded, rate = ffmpeg.decode(cut)
    except ffmpeg.DecodeError as error:
        assert cut.name in str(error)
        return
    assert rate == SAMPLERATE and decoded.shape[1] == 2
    assert 0 < decoded.shape[0] < len(_tones())
