"""Il demuxer aac (ADTS, i file .aac "nudi") della build minima (D9).

La build minima non ha il muxer adts: il test codifica in .m4a e poi
riavvolge ogni pacchetto AAC con un'intestazione ADTS di 7 byte, come
farebbe un muxer. Il .m4a di ffmpeg ha una sola traccia, con i pacchetti
in fila in mdat e le loro dimensioni in stsz.
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

SECONDS = 1.5
CHANNEL_HZ = (440.0, 660.0)
# indice di frequenza ADTS (ISO 14496-3, tabella 1.18)
RATE_INDEX = {96000: 0, 88200: 1, 64000: 2, 48000: 3, 44100: 4, 32000: 5,
              24000: 6, 22050: 7, 16000: 8, 12000: 9, 11025: 10, 8000: 11}
AAC_LC_PROFILE = 1  # profilo ADTS = object type - 1; AAC LC = 2
ADTS_HEADER_BYTES = 7
# in ADTS nessuna edit list toglie il priming (1024) né il riempimento
# dell'ultimo frame: la lunghezza torna entro tre frame
LENGTH_SLACK = 3 * 1024
PITCH_TOL_HZ = 4.0


def _adts_header(payload_bytes: int, rate: int, channels: int) -> bytes:
    length = payload_bytes + ADTS_HEADER_BYTES
    bits = (0xFFF << 44) | (1 << 40)  # sync, MPEG-4, layer 0, senza CRC
    bits |= (AAC_LC_PROFILE << 38) | (RATE_INDEX[rate] << 34) | (channels << 30)
    bits |= (length << 13) | (0x7FF << 2)  # buffer fullness "variabile"
    return bits.to_bytes(ADTS_HEADER_BYTES, "big")


def _packets(m4a: bytes) -> list[bytes]:
    stsz = m4a.index(b"stsz")
    count = struct.unpack_from(">I", m4a, stsz + 12)[0]
    sizes = struct.unpack_from(f">{count}I", m4a, stsz + 16)
    pos = m4a.index(b"mdat") + 4
    packets = []
    for size in sizes:
        packets.append(m4a[pos : pos + size])
        pos += size
    return packets


def _tones(samplerate: int, channels: int = 2) -> np.ndarray:
    t = np.arange(int(samplerate * SECONDS)) / samplerate
    rows = [0.5 * np.sin(2 * np.pi * hz * t) for hz in CHANNEL_HZ[:channels]]
    return np.stack(rows).astype(np.float32)


def adts_bytes(tmp_path: Path, samplerate: int, channels: int = 2) -> tuple[bytes, int]:
    """Un flusso ADTS e il numero di frame audio da cui nasce."""
    source = _tones(samplerate, channels)
    m4a = ffmpeg.encode_fixture(source, samplerate, tmp_path / "base.m4a", "aac")
    packets = _packets(m4a.read_bytes())
    stream = b"".join(_adts_header(len(p), samplerate, channels) + p for p in packets)
    return stream, source.shape[1]


def write_adts(tmp_path: Path, samplerate: int) -> tuple[Path, int]:
    stream, frames = adts_bytes(tmp_path, samplerate)
    dest = tmp_path / "nudo.aac"
    dest.write_bytes(stream)
    return dest, frames


@pytest.mark.parametrize("samplerate", [22050, 44100, 48000])
def test_adts_keeps_rate_length_and_pitch(tmp_path, samplerate):
    path, frames = write_adts(tmp_path, samplerate)
    decoded, rate = ffmpeg.decode(path)
    assert rate == samplerate and decoded.shape[1] == 2
    assert abs(decoded.shape[0] - frames) <= LENGTH_SLACK
    middle = decoded[samplerate // 4 : samplerate, :]
    for channel, hz in enumerate(CHANNEL_HZ):
        spectrum = np.abs(np.fft.rfft(middle[:, channel] * np.hanning(len(middle))))
        found = float(np.argmax(spectrum)) * samplerate / len(middle)
        assert found == pytest.approx(hz, abs=PITCH_TOL_HZ)


def test_adts_without_sync_is_not_audio(tmp_path):
    path, _ = write_adts(tmp_path, 44100)
    broken = tmp_path / "rotto.aac"
    broken.write_bytes(bytes(b ^ 0xFF for b in path.read_bytes()[:20000]))
    with pytest.raises(ffmpeg.DecodeError):
        ffmpeg.decode(broken)


def test_format_change_mid_stream_keeps_the_first_shape(tmp_path):
    # una registrazione radio in ADTS puo' passare da stereo a mono e
    # cambiare sample rate a meta': l'array resta [frames, canali iniziali]
    # al sample rate iniziale, e il mono finisce in entrambi i canali
    stereo, stereo_frames = adts_bytes(tmp_path, 44100, 2)
    mono, mono_frames = adts_bytes(tmp_path, 48000, 1)
    path = tmp_path / "cambia.aac"
    path.write_bytes(stereo + mono)
    decoded, rate = ffmpeg.decode(path)
    assert rate == 44100 and decoded.shape[1] == 2
    expected = stereo_frames + round(mono_frames * 44100 / 48000)
    assert abs(decoded.shape[0] - expected) <= 2 * LENGTH_SLACK
    tail = decoded[-44100 : -44100 // 4, :]
    for channel in range(2):
        spectrum = np.abs(np.fft.rfft(tail[:, channel] * np.hanning(len(tail))))
        found = float(np.argmax(spectrum)) * 44100 / len(tail)
        assert found == pytest.approx(CHANNEL_HZ[0], abs=PITCH_TOL_HZ)
