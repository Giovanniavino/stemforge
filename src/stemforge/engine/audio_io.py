"""I/O audio del motore: decodifica, resampling, blocchi per file lunghi.

BUILD_SPEC §5.7. La SCRITTURA degli stem non sta qui ma in export/folder.py:
il diagramma delle dipendenze (§3) vieta a export di importare engine, e i
due mondi condividono solo numpy.

- Decodifica sempre a float32 (regola 1).
- soundfile copre wav/flac/ogg/aiff/mp3; per m4a/aac si passa da un
  ffmpeg esterno (bundled nell'app o sul PATH). Se manca, errore chiaro.
- Il resampling usa torchaudio (sinc kaiser di qualità) ed è pigro:
  i test unitari girano senza torch.
- File lunghi: blocchi con rampe lineari COMPLEMENTARI che sommano a 1
  in ogni campione (regola 6): un crossfade equal-power romperebbe
  l'invariante di ricostruzione.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_SAMPLERATE = 44100
MAX_DURATION_S = 30 * 60  # limite duro (§5.7 regola 6)
BLOCK_THRESHOLD_S = 15 * 60
BLOCK_LENGTH_S = 300.0
BLOCK_OVERLAP_S = 2.0

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}


class UnsupportedFormatError(ValueError):
    """Formato non decodificabile: da rifiutare al drop, non a metà (§10.1)."""


class TooLongError(ValueError):
    """Brano oltre il limite duro dei 30 minuti (§5.7)."""


@dataclass(frozen=True)
class SourceAudio:
    data: np.ndarray  # [channels, samples] float32
    samplerate: int
    original_channels: int  # per riscrivere mono in uscita (regola 3)
    original_frames: int  # lunghezza esatta da restituire (regola 2)

    @property
    def duration_s(self) -> float:
        return self.original_frames / self.samplerate


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _decode_via_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        raise UnsupportedFormatError(
            f"Non so decodificare {path.name}: serve ffmpeg per questo formato. "
            "Converti il file in WAV/FLAC/MP3 oppure installa ffmpeg."
        )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "decoded.wav"
        proc = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(path), "-acodec", "pcm_f32le", str(out)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise UnsupportedFormatError(
                f"File audio non leggibile: {path.name}. "
                f"Dettaglio: {proc.stderr.strip()[:200]}"
            )
        data, samplerate = sf.read(out, dtype="float32", always_2d=True)
    return data, samplerate


def load(path: Path) -> SourceAudio:
    """Carica un file audio come [channels, samples] float32.

    Mono viene duplicato su due canali per il modello (regola 3);
    `original_channels` ricorda com'era per la riscrittura.
    """
    try:
        data, samplerate = sf.read(path, dtype="float32", always_2d=True)
    except (sf.LibsndfileError, RuntimeError):
        data, samplerate = _decode_via_ffmpeg(path)
    frames = data.shape[0]
    if frames == 0:
        raise UnsupportedFormatError(f"File audio vuoto: {path.name}")
    if frames / samplerate > MAX_DURATION_S:
        raise TooLongError(
            f"{path.name} dura più di 30 minuti: StemForge non lo elabora. "
            "Taglia il file nella DAW e riprova."
        )
    channels = data.shape[1]
    audio = data.T.copy()  # [C, S]
    if channels == 1:
        audio = np.repeat(audio, 2, axis=0)
    elif channels > 2:
        # I modelli sono stereo: downmix dei canali extra, dichiarato.
        audio = np.stack([audio[0], audio[1]])
    return SourceAudio(
        data=np.ascontiguousarray(audio, dtype=np.float32),
        samplerate=samplerate,
        original_channels=min(channels, 2),
        original_frames=frames,
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


@dataclass(frozen=True)
class Block:
    start: int  # campioni, inclusivo
    end: int  # campioni, esclusivo
    fade_in: int  # campioni di rampa complementare all'inizio


def split_blocks(total_frames: int, samplerate: int) -> tuple[Block, ...]:
    """Blocchi per file oltre i 15 minuti (regola 6). Sotto soglia: uno."""
    if total_frames / samplerate <= BLOCK_THRESHOLD_S:
        return (Block(0, total_frames, 0),)
    length = int(BLOCK_LENGTH_S * samplerate)
    overlap = int(BLOCK_OVERLAP_S * samplerate)
    blocks: list[Block] = []
    start = 0
    while start < total_frames:
        end = min(start + length, total_frames)
        blocks.append(Block(start, end, 0 if start == 0 else overlap))
        if end == total_frames:
            break
        start = end - overlap
    return tuple(blocks)


def overlap_add(dest: np.ndarray, chunk: np.ndarray, block: Block) -> None:
    """Accumula un blocco elaborato con rampe lineari complementari.

    Nella zona di sovrapposizione dest contiene già la coda del blocco
    precedente: qui si applica w crescente al nuovo e (1-w) al vecchio,
    e w + (1-w) == 1 esattamente in ogni campione.
    """
    fade = block.fade_in
    if fade > 0:
        w = np.linspace(0.0, 1.0, fade, endpoint=False, dtype=np.float32)
        dest[..., block.start : block.start + fade] *= 1.0 - w
        dest[..., block.start : block.start + fade] += chunk[..., :fade] * w
        dest[..., block.start + fade : block.end] = chunk[..., fade:]
    else:
        dest[..., block.start : block.end] = chunk
