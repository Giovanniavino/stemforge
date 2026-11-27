"""Layout multicanale non di default: decode li restituisce intatti (D9, §5.7.7).

Il downmix ITU è di audio_io e lavora sui canali come arrivano. Se il
decoder rimescolasse un 6.0 o un esagonale verso il 5.1 di default, la
voce (centro) e i surround finirebbero sommati prima ancora del downmix.
I WAV si compongono qui, WAVE_FORMAT_EXTENSIBLE con la maschera voluta.
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
CHANNEL_HZ = (220.0, 440.0, 660.0, 880.0, 1100.0, 1320.0, 1540.0, 1760.0)
EXTENSIBLE = 0xFFFE
CB_SIZE = 22
FLOAT_BITS = 32
KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = bytes.fromhex("0300000000001000800000aa00389b71")

# maschere WAVEFORMATEXTENSIBLE (FL=0x1 FR=0x2 FC=0x4 LFE=0x8 BL=0x10
# BR=0x20 FLC=0x40 FRC=0x80 BC=0x100 SL=0x200 SR=0x400)
LAYOUTS = {
    "hexagonal": (0x137, 6),
    "6.0": (0x707, 6),
    "5.1(side)": (0x60F, 6),
    "7.1(wide)": (0xFF, 8),
    "senza maschera": (0, 6),
}


def write_extensible_wav(path: Path, audio: np.ndarray, mask: int) -> Path:
    """audio [frames, channels] float32 in un WAV con maschera dei canali."""
    channels = audio.shape[1]
    block = channels * FLOAT_BITS // 8
    fmt = struct.pack("<HHIIHHHHI", EXTENSIBLE, channels, SAMPLERATE, SAMPLERATE * block,
                      block, FLOAT_BITS, CB_SIZE, FLOAT_BITS, mask)
    fmt += KSDATAFORMAT_SUBTYPE_IEEE_FLOAT
    data = audio.astype("<f4").tobytes()
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_every_channel_comes_back_untouched(tmp_path, layout):
    mask, channels = LAYOUTS[layout]
    t = np.arange(SAMPLERATE) / SAMPLERATE
    source = np.stack([0.3 * np.sin(2 * np.pi * CHANNEL_HZ[k] * t) for k in range(channels)],
                      axis=1).astype(np.float32)
    path = write_extensible_wav(tmp_path / "surround.wav", source, mask)
    decoded, rate = ffmpeg.decode(path)
    assert rate == SAMPLERATE
    assert np.array_equal(decoded, source)
