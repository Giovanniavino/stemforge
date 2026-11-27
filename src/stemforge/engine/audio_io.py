"""I/O audio del motore: caricamento, resampling, lunghezze, canali.

BUILD_SPEC §5.7. La SCRITTURA degli stem non sta qui ma in export/folder.py:
il diagramma delle dipendenze (§3) vieta a export di importare engine, e i
due mondi condividono solo numpy. La decodifica sta in decode.py, i
blocchi per i file lunghi in blocks.py.

- Decodifica sempre a float32 (regola 1), con TUTTI i canali del file.
- Multicanale: downmix stereo ITU-R BS.775 (regola 7, engine/downmix.py),
  dichiarato all'utente con un avviso dalla pipeline. Tenere i primi due
  canali butterebbe via il centro, cioè la voce.
- NaN/Inf: il file si rifiuta (regola 8), mai si passa al modello.
- Il resampling usa torchaudio (sinc kaiser di qualità) ed è pigro:
  i test unitari girano senza torch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from stemforge.engine import decode, downmix
from stemforge.engine.blocks import (
    BLOCK_LENGTH_S,
    BLOCK_OVERLAP_S,
    BLOCK_THRESHOLD_S,
    Block,
    block_length_s,
    overlap_add,
    split_blocks,
)
from stemforge.engine.decode import SUPPORTED_EXTENSIONS, probe_duration
from stemforge.engine.errors import (
    NonFiniteAudioError,
    TooLongError,
    UnsupportedFormatError,
)

__all__ = [
    "BLOCK_LENGTH_S", "BLOCK_OVERLAP_S", "BLOCK_THRESHOLD_S", "Block",
    "SUPPORTED_EXTENSIONS", "NonFiniteAudioError", "TooLongError",
    "UnsupportedFormatError", "block_length_s", "overlap_add", "probe_duration",
    "split_blocks",
]

MODEL_SAMPLERATE = 44100
MAX_DURATION_S = 30 * 60  # limite duro (§5.7 regola 6)


@dataclass(frozen=True)
class SourceAudio:
    data: np.ndarray  # [2, samples] float32: sempre stereo per il modello
    samplerate: int
    original_channels: int  # canali degli stem in uscita: 1 o 2 (regole 3 e 7)
    original_frames: int  # lunghezza esatta da restituire (regola 2)
    source_channels: int = 2  # canali del file; > 2 = downmix dichiarato

    @property
    def duration_s(self) -> float:
        return self.original_frames / self.samplerate

    @property
    def downmixed(self) -> bool:
        return self.source_channels > 2


def _refuse_if_too_long(path: Path, seconds: float | None) -> None:
    if seconds is not None and seconds > MAX_DURATION_S:
        raise TooLongError(
            "err.too_long", f"{seconds:.1f} s", name=path.name, minutes=math.ceil(seconds / 60)
        )


def _refuse_non_finite(data: np.ndarray, path: Path) -> None:
    # Una somma in float64 non va mai in overflow su campioni float32 di
    # un brano, e NaN/Inf la contaminano: stessa risposta di
    # np.isfinite(data).all() senza un array booleano grande quanto il file.
    if not math.isfinite(float(np.sum(data, dtype=np.float64))):
        raise NonFiniteAudioError("err.non_finite", name=path.name)


def _to_model_channels(data: np.ndarray, path: Path) -> np.ndarray:
    """[frames, channels] del file -> [2, frames] per il modello."""
    channels = data.shape[1]
    if channels == 1:
        return np.repeat(data.T, 2, axis=0)
    if channels == 2:
        return data.T
    if channels > downmix.MAX_CHANNELS:
        raise UnsupportedFormatError("err.channels", name=path.name, channels=channels)
    return downmix.to_stereo(data.T)


def load(path: Path) -> SourceAudio:
    """Carica un file audio come [2, samples] float32 per il modello.

    Mono viene duplicato su due canali (regola 3), il multicanale ridotto
    a stereo (regola 7); `original_channels` dice come riscrivere gli stem.
    """
    path = Path(path)
    # dall'intestazione, PRIMA di decodificare 30+ minuti per niente
    _refuse_if_too_long(path, decode.probe_duration(path))
    data, samplerate = decode.read(path)
    frames, channels = data.shape
    if frames == 0 or channels == 0 or samplerate <= 0:
        raise UnsupportedFormatError("err.empty", name=path.name)
    _refuse_if_too_long(path, frames / samplerate)
    _refuse_non_finite(data, path)
    audio = _to_model_channels(data, path)
    return SourceAudio(
        data=np.ascontiguousarray(audio, dtype=np.float32),
        samplerate=samplerate,
        original_channels=1 if channels == 1 else 2,
        original_frames=frames,
        source_channels=channels,
    )


def resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Resampling sinc di qualità via torchaudio. Import pigro."""
    if sr_from == sr_to:
        return audio
    import torch
    import torchaudio.functional as taf

    tensor = torch.from_numpy(np.ascontiguousarray(audio))
    out = taf.resample(
        tensor,
        orig_freq=sr_from,
        new_freq=sr_to,
        lowpass_filter_width=64,
        rolloff=0.9475937167399596,
        resampling_method="sinc_interp_kaiser",
        beta=14.769656459379492,
    )
    return out.numpy().astype(np.float32, copy=False)


def match_length(audio: np.ndarray, frames: int) -> np.ndarray:
    """Tronca o azzera-in-coda alla lunghezza esatta (regola 2).

    Anche un solo campione di scarto manda fuori sync lo stem nel
    progetto: la lunghezza si impone, non si spera.
    """
    current = audio.shape[-1]
    if current == frames:
        return audio
    if current > frames:
        return audio[..., :frames]
    pad = np.zeros((*audio.shape[:-1], frames - current), dtype=audio.dtype)
    return np.concatenate([audio, pad], axis=-1)


def to_original_channels(audio: np.ndarray, original_channels: int) -> np.ndarray:
    """Stereo del modello -> canali del sorgente (regola 3).

    Il mono torna mono con la media dei due canali, che per un sorgente
    mono duplicato è identica al canale originale.
    """
    if original_channels == 1:
        return audio.mean(axis=0, keepdims=True)
    return audio
