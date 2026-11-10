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
sono MISURATE (picco della memoria privata del processo, insieme
htdemucs_ft completo, CPU, torch 2.10 e 2.2.2): i numeri e il metodo
stanno nel commit che li ha introdotti. Con la RAM sconosciuta si
resta ai blocchi di sempre. `segment` non si tocca (§6.2).

Se la RAM non basta nemmeno per un brano sotto i 15 minuti, si divide
anche quello: l'invariante regge per costruzione con qualunque numero
di blocchi, lo swap no.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BLOCK_THRESHOLD_S = 15 * 60
BLOCK_LENGTH_S = 300.0  # tetto: più RAM non dà più qualità
BLOCK_OVERLAP_S = 2.0
# Sotto i 30 s la sovrapposizione di 2 s pesa più del 7% del calcolo, e
# una macchina che non regge 30 s di audio non regge neanche il modello.
MIN_BLOCK_S = 30.0

# Misurati: vedi la docstring del modulo.
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
