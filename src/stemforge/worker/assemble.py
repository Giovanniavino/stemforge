"""Assemblaggio e scrittura degli output di un job.

BUILD_SPEC §5.1.1, §5.2.4, §7.3. Qui gli stem tornano al sample rate e
ai canali del sorgente, i residui si calcolano per sottrazione dal mix
originale (esatti per costruzione, §10.2) e tutto finisce su disco via
export/folder.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import numpy as np

from stemforge import __version__
from stemforge.engine import audio_io
from stemforge.engine.planner import Pass, Plan, subtraction_terms
from stemforge.export import folder
from stemforge.model.job import JobResult, SeparationJob, StemFile
from stemforge.model.stem import StemKind
from stemforge.worker import protocol

Emit = Callable[[protocol.Message], None]


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_original(audio: np.ndarray, source: audio_io.SourceAudio) -> np.ndarray:
    out = audio_io.resample(audio, audio_io.MODEL_SAMPLERATE, source.samplerate)
    out = audio_io.match_length(out, source.original_frames)
    return audio_io.to_original_channels(out, source.original_channels)


def effective_write(job: SeparationJob, unavailable: list[Pass]) -> tuple[StemKind, ...]:
    """Cosa scrivere davvero: se un 2° stadio è indisponibile, i suoi
    derivati escono dalla lista e al loro posto entra lo stem base
    (§5.2.4: "drums.wav invece di kick e snare")."""
    write: list[StemKind] = list(job.wanted)
    for p in unavailable:
        if p.backend == "dereverb":
            continue  # la voce resta com'è, nessuna sostituzione
        removed_at: int | None = None
        for kind in p.needed:
            if kind in write:
                index = write.index(kind)
                removed_at = index if removed_at is None else min(removed_at, index)
                write.remove(kind)
        assert p.input_stem is not None
        if p.input_stem not in write:
            write.insert(removed_at if removed_at is not None else len(write), p.input_stem)
    return tuple(write)


def _residuals(
    write: tuple[StemKind, ...],
    mix: np.ndarray,
    out: dict[StemKind, np.ndarray],
    stems: dict[StemKind, np.ndarray],
    vocals_stage1: np.ndarray | None,
    source: audio_io.SourceAudio,
) -> None:
    if StemKind.INSTRUMENTAL in write:
        assert vocals_stage1 is not None
        out[StemKind.INSTRUMENTAL] = mix - vocals_stage1
    if StemKind.OTHER in write:
        terms = subtraction_terms(write)
        if not terms and StemKind.OTHER in stems:
            # `other` da solo: viene dal sotto-modello dedicato (§5.3)
            out[StemKind.OTHER] = to_original(stems[StemKind.OTHER], source)
        else:
            acc = mix.copy()
            for term in terms:
                if term == StemKind.VOCALS and vocals_stage1 is not None:
                    acc -= vocals_stage1
                else:
                    acc -= out[term]
            out[StemKind.OTHER] = acc


def assemble_outputs(
    write: tuple[StemKind, ...],
    source: audio_io.SourceAudio,
    stage1: dict[StemKind, np.ndarray],
    stems: dict[StemKind, np.ndarray],
) -> dict[StemKind, np.ndarray]:
    """Porta gli stem al sample rate/canali originali e calcola i
    residui per sottrazione dal mix originale (esatti per costruzione)."""
    mix = audio_io.to_original_channels(source.data, source.original_channels)
    out: dict[StemKind, np.ndarray] = {}
    for kind in write:
        if kind in (StemKind.OTHER, StemKind.INSTRUMENTAL):
            continue
        out[kind] = to_original(stems[kind], source)
    if StemKind.INSTRUMENTAL in write or StemKind.OTHER in write:
        # la sottrazione usa la voce del 1° stadio (wet), §5.2.3
        vocals_stage1 = (
            to_original(stage1[StemKind.VOCALS], source)
            if StemKind.VOCALS in stage1
            else None
        )
        _residuals(write, mix, out, stems, vocals_stage1, source)
    return out


def _write_files(
    job: SeparationJob,
    write: tuple[StemKind, ...],
    source: audio_io.SourceAudio,
    out_dir: Path,
    outputs: dict[StemKind, np.ndarray],
    wet: np.ndarray | None,
) -> list[folder.WrittenStem]:
    written: list[folder.WrittenStem] = []
    for kind in write:
        written.append(
            folder.write_stem(out_dir, kind, outputs[kind], source.samplerate, job.fmt)
        )
    if wet is not None:
        written.append(
            folder.write_stem(
                out_dir,
                StemKind.VOCALS,
                to_original(wet, source),
                source.samplerate,
                job.fmt,
                filename=f"vocals_wet.{job.fmt}",
            )
        )
    return written


def write_all(
    job: SeparationJob,
    write: tuple[StemKind, ...],
    source: audio_io.SourceAudio,
    out_dir: Path,
    outputs: dict[StemKind, np.ndarray],
    wet: np.ndarray | None,
    plan_: Plan,
    warnings: list[str],
    emit: Emit,
) -> JobResult:
    emit(protocol.Phase(label="Scrittura stem", pass_index=len(plan_.passes) + 1,
                        pass_count=len(plan_.passes) + 1))
    written = _write_files(job, write, source, out_dir, outputs, wet)
    dereverb_applied = wet is not None
    for w in written:
        if w.nearly_silent:
            warnings.append(f"{w.path.name} è quasi silenzioso (picco {w.peak_dbfs:.0f} dBFS)")
    folder.write_manifest(
        out_dir=out_dir,
        source_name=job.source.name,
        source_sha1=sha1_of(job.source),
        duration_s=round(source.duration_s, 3),
        samplerate=source.samplerate,
        channels=source.original_channels,
        backend="demucs",
        model=plan_.first_stage_model,
        quality=job.quality,
        version=__version__,
        written=written,
        dereverb=dereverb_applied,
    )
    return JobResult(
        out_dir=out_dir,
        stems=tuple(
            StemFile(w.kind, w.path.name, round(w.peak_dbfs, 2), round(w.rms_dbfs, 2))
            for w in written
        ),
        warnings=tuple(warnings),
    )
