"""Blocchi per i file lunghi e per le macchine con poca RAM (§5.7, §6.1).

BUILD_SPEC §5.7 regola 6: oltre i 15 minuti si elabora a blocchi con
rampe lineari COMPLEMENTARI che sommano a 1 in ogni campione (un
crossfade equal-power romperebbe l'invariante di ricostruzione, §10.2).

§6.1 punto 3: la lunghezza dei blocchi si adatta alla RAM disponibile,
perché un Mac da 4-8 GB che swappa trasforma "lento ma va" in "non
finisce mai". La memoria di una passata Demucs è una parte fissa (le
attivazioni di un segmento da 7.8 s, che non dipendono dalla lunghezza)
più una parte proporzionale ai secondi di audio del blocco (gli
accumulatori di apply_model e le uscite di ogni sorgente). Entrambe
sono MISURATE (picco della memoria privata del processo oltre il
modello già caricato, htdemucs_ft completo, preset best, CPU, 20 e 60 s
di audio): torch 2.10 ~0.92 GB + 10.5 MB/s, torch 2.2.2 ~0.62 GB +
10.75 MB/s. Le costanti sotto sono il caso peggiore più un margine.
Con la RAM sconosciuta si resta ai blocchi di sempre. `segment` non si tocca (§6.2).

Se la RAM non basta nemmeno per un brano sotto i 15 minuti, si divide
anche quello: l'invariante regge per costruzione con qualunque numero
di blocchi, lo swap no.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

BLOCK_THRESHOLD_S = 15 * 60
BLOCK_LENGTH_S = 300.0  # tetto: più RAM non dà più qualità
BLOCK_OVERLAP_S = 2.0
# Sotto i 30 s la sovrapposizione di 2 s pesa più del 7% del calcolo, e
# una macchina che non regge 30 s di audio non regge neanche il modello.
MIN_BLOCK_S = 30.0

# Misurati con margine: vedi la docstring del modulo.
PASS_FIXED_BYTES = 1_200_000_000
PASS_BYTES_PER_AUDIO_S = 12_000_000
# Quota della RAM disponibile che una passata può prendersi: il resto
# resta al sistema, alla cache dei file e agli array del brano intero.
RAM_FRACTION = 0.7


@dataclass(frozen=True)
class Block:
    start: int  # campioni, inclusivo
    end: int  # campioni, esclusivo
    fade_in: int  # campioni di rampa complementare all'inizio


def output_bytes(sources: int, channels: int, frames: int) -> int:
    """Byte degli stem di una passata a lunghezza PIENA (float32).

    Restano in RAM per tutto il brano qualunque sia la lunghezza dei
    blocchi: su 30 minuti e 4 sorgenti sono 1.3 GB.
    """
    return sources * channels * frames * np.dtype(np.float32).itemsize


def memory_for_blocks(available_bytes: int | None, full_length_bytes: int) -> int | None:
    """RAM che resta ai blocchi dopo gli stem a lunghezza piena; None se ignota."""
    # shortcut: gli stem pieni restano in RAM, quindi sotto ~3.3 GB liberi un job di
    # 20 min a 4 stem supera la RAM anche coi blocchi minimi; scriverli su disco a
    # blocchi se il Mac da 4 GB va in swap (manual_checklist dell'area E).
    if available_bytes is None:
        return None
    return max(0, available_bytes - full_length_bytes)


def fitting_seconds(available_bytes: int | None) -> float:
    """Secondi di audio che una passata regge senza swap; inf se la RAM è ignota."""
    if available_bytes is None:
        return float("inf")
    budget = available_bytes * RAM_FRACTION - PASS_FIXED_BYTES
    return max(0.0, budget / PASS_BYTES_PER_AUDIO_S)


def block_length_s(available_bytes: int | None) -> float:
    """Lunghezza dei blocchi per la RAM data, fra MIN_BLOCK_S e BLOCK_LENGTH_S."""
    return min(BLOCK_LENGTH_S, max(MIN_BLOCK_S, fitting_seconds(available_bytes)))


def split_blocks(
    total_frames: int, samplerate: int, available_bytes: int | None = None
) -> tuple[Block, ...]:
    """Blocchi di un file. Un blocco solo se il brano è sotto i 15 minuti
    E sta nella RAM; altrimenti blocchi sovrapposti di block_length_s()."""
    duration = total_frames / samplerate
    if duration <= BLOCK_THRESHOLD_S and duration <= fitting_seconds(available_bytes):
        return (Block(0, total_frames, 0),)
    length = int(block_length_s(available_bytes) * samplerate)
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


def overlap_add(dest: NDArray[np.float32], chunk: NDArray[np.float32], block: Block) -> None:
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
