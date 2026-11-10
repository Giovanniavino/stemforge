"""Controlli PRIMA di iniziare un job: lo spazio su disco (§10.1).

La stima viene dal piano, non da un fattore fisso: file scritti × durata
× byterate degli stem in uscita, +20% di margine (export/folder.py).

- I canali sono quelli degli STEM, non del file: un 5.1 esce stereo
  (§5.7 regola 7), un mono esce mono (regola 3).
- Il sample rate è quello del sorgente: gli stem tornano lì (regola 2).
- Il de-riverbero scrive anche `vocals_wet` (§5.2.3): un file in più.
- FLAC si stima come PCM 24 bit: è il caso peggiore (un FLAC di rumore
  non comprime e ha qualche byte di intestazione per frame, che il
  margine copre), e sbagliare per eccesso costa solo un avviso inutile.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from stemforge.engine.audio_io import SourceAudio
from stemforge.engine.errors import InsufficientDiskError
from stemforge.export import folder
from stemforge.model.job import SeparationJob

_MB = 1_000_000


def free_bytes(target: Path) -> int:
    """Spazio libero sul volume dove finirà `target`, anche se non esiste ancora."""
    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def files_written(job: SeparationJob) -> int:
    return len(job.wanted) + (1 if job.dereverb_vocals else 0)


def needed_bytes(job: SeparationJob, source: SourceAudio) -> int:
    return folder.estimate_disk_bytes(
        n_stems=files_written(job),
        duration_s=source.duration_s,
        samplerate=source.samplerate,
        channels=source.original_channels,
    )


def check_disk(
    job: SeparationJob, source: SourceAudio, free: Callable[[Path], int] = free_bytes
) -> None:
    needed = needed_bytes(job, source)
    available = free(job.out_dir)
    if available < needed:
        raise InsufficientDiskError(
            "err.disk_precheck",
            f"servono {needed} byte, liberi {available}",
            folder=str(job.out_dir),
            needed=max(1, -(-needed // _MB)),
            free=available // _MB,
        )
