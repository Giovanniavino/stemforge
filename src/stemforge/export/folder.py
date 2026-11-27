"""Scrittura degli stem su disco: cartella, WAV/FLAC 24 bit, manifest.

BUILD_SPEC §7.3, §5.7. Regole incorporate:
- nome cartella = sorgente senza estensione; collisione -> " (2)", mai
  sovrascrittura silenziosa;
- nomi file = valore di StemKind (Ableton li usa come nome traccia);
- 24 bit PCM sempre, WAV e FLAC (regola 4);
- nessuna normalizzazione (regola 5): qui si scrive, non si tocca;
- i file sono chiusi prima che il chiamante li dichiari pronti (§7.2);
- traccia sotto -60 dBFS: si scrive comunque, con avviso (§10.1).
"""

from __future__ import annotations

import errno
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf

from stemforge.model.job import StemFile
from stemforge.model.manifest import AudioInfo, EngineInfo, Manifest, SourceInfo
from stemforge.model.stem import StemKind

BIT_DEPTH = 24
SILENCE_THRESHOLD_DBFS = -60.0
_FLOOR_DBFS = -120.0  # valore convenzionale per il silenzio digitale


def dbfs(value: float) -> float:
    if value <= 0.0:
        return _FLOOR_DBFS
    return max(_FLOOR_DBFS, 20.0 * math.log10(value))


def peak_dbfs(audio: np.ndarray) -> float:
    return dbfs(float(np.max(np.abs(audio), initial=0.0)))


def rms_dbfs(audio: np.ndarray) -> float:
    return dbfs(float(np.sqrt(np.mean(np.square(audio, dtype=np.float64)))))


def allocate_out_dir(base: Path, source_name: str) -> Path:
    """Cartella del job, con suffisso " (2)", " (3)"... in collisione."""
    stem_name = Path(source_name).stem
    candidate = base / stem_name
    counter = 2
    while candidate.exists():
        candidate = base / f"{stem_name} ({counter})"
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def _raise_if_disk_full(out_dir: Path, audio: np.ndarray, exc: Exception) -> None:
    """libsndfile non dice "disco pieno": dice "errore di scrittura".

    Se dopo il guasto sul volume non c'è più posto per lo stem, la causa
    è quella, e diventa un OSError(ENOSPC) che il worker traduce in un
    messaggio che dice cosa fare (§10.1). Qui non si importa engine (§3).
    """
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return  # già nella forma giusta: lo rilancia il chiamante
    stem_bytes = audio.shape[-1] * audio.shape[0] * (BIT_DEPTH // 8)
    try:
        free = shutil.disk_usage(out_dir).free
    except OSError:
        return  # il volume è sparito: non è un disco pieno
    if free < stem_bytes:
        raise OSError(errno.ENOSPC, f"disco pieno scrivendo in {out_dir}: {exc}") from exc


@dataclass(frozen=True)
class WrittenStem:
    kind: StemKind
    path: Path
    peak_dbfs: float
    rms_dbfs: float
    nearly_silent: bool


def write_stem(
    out_dir: Path,
    kind: StemKind,
    audio: np.ndarray,  # [channels, samples] float32
    samplerate: int,
    fmt: str,
    filename: str | None = None,
) -> WrittenStem:
    name = filename if filename is not None else f"{kind.value}.{fmt}"
    path = out_dir / name
    subtype = "PCM_24"
    try:
        # soundfile vuole [samples, channels]
        sf.write(path, audio.T, samplerate, subtype=subtype, format=fmt.upper())
    except (RuntimeError, OSError) as exc:
        _raise_if_disk_full(out_dir, audio, exc)
        raise
    peak = peak_dbfs(audio)
    return WrittenStem(
        kind=kind,
        path=path,
        peak_dbfs=peak,
        rms_dbfs=rms_dbfs(audio),
        nearly_silent=peak < SILENCE_THRESHOLD_DBFS,
    )


def write_manifest(
    out_dir: Path,
    source_name: str,
    source_sha1: str,
    duration_s: float,
    samplerate: int,
    channels: int,
    backend: str,
    model: str,
    quality: str,
    version: str,
    written: list[WrittenStem],
    dereverb: bool,
) -> Path:
    manifest = Manifest(
        source=SourceInfo(name=source_name, sha1=source_sha1, duration_s=duration_s),
        audio=AudioInfo(samplerate=samplerate, channels=channels, bit_depth=BIT_DEPTH),
        engine=EngineInfo(backend=backend, model=model, quality=quality, version=version),
        stems=tuple(
            StemFile(
                kind=w.kind,
                file=w.path.name,
                peak_dbfs=round(w.peak_dbfs, 2),
                rms_dbfs=round(w.rms_dbfs, 2),
            )
            for w in written
        ),
        created_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        dereverb=dereverb,
    )
    path = out_dir / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    return path


def estimate_disk_bytes(n_stems: int, duration_s: float, samplerate: int, channels: int) -> int:
    """Stima dal piano (§10.1): n_stem x durata x byterate, +20% di margine."""
    byterate = samplerate * channels * (BIT_DEPTH // 8)
    return int(n_stems * duration_s * byterate * 1.2)
