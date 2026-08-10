"""La pipeline di esecuzione di un SeparationJob.

BUILD_SPEC D2, §5.3, §8.3. Serve sia il worker (runner.py) che la CLI:
run_job è l'unico punto in cui piano, backend ed export si incontrano.

Decisioni non ovvie, con la ragione:
- La cartella di output si alloca PRIMA dell'inferenza e si annuncia
  con `Started`: se l'utente annulla, il padre sa cosa ripulire.
- `other` e `instrumental` si calcolano per sottrazione AL SAMPLE RATE
  ORIGINALE, dal mix originale: così l'invariante di ricostruzione
  (§10.2) regge esattamente anche dopo il round-trip di resampling.
- Con de-riverbero attivo la sottrazione usa la voce WET (l'uscita vera
  del 1° stadio): il riverbero rimosso non deve finire dentro `other`.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from stemforge import __version__
from stemforge.engine import audio_io, calibrate
from stemforge.engine.contract import Backend, BackendUnavailable, CancelledError, effective_quality
from stemforge.engine.device import resolve_device
from stemforge.engine.planner import (
    Pass,
    Plan,
    demucs_factors,
    estimate_pass_seconds,
    plan,
    subtraction_terms,
)
from stemforge.engine.registry import create_backend
from stemforge.export import folder
from stemforge.model.job import JobResult, SeparationJob, StemFile
from stemforge.model.stem import StemKind
from stemforge.worker import assemble, protocol

Emit = Callable[[protocol.Message], None]
BackendCache = dict[tuple[str, str, str, str], Backend]

_MIN_PROGRESS_STEP = 0.005


class _Progress:
    """Avanzamento globale = somma pesata dei costi delle passate (§8.3),
    monotòno per costruzione."""

    def __init__(self, emit: Emit, weights: list[float]) -> None:
        total = sum(weights) or 1.0
        self._fractions = [w / total for w in weights]
        self._emit = emit
        self._done = 0.0
        self._last = -1.0

    def pass_callback(self, pass_index: int) -> Callable[[float], None]:
        base = sum(self._fractions[:pass_index])
        weight = self._fractions[pass_index]

        def callback(value: float) -> None:
            self._report(base + weight * min(1.0, max(0.0, value)))

        return callback

    def complete_pass(self, pass_index: int) -> None:
        self._done = sum(self._fractions[: pass_index + 1])
        self._report(self._done)

    def _report(self, value: float) -> None:
        value = max(self._last, value)
        if value - self._last >= _MIN_PROGRESS_STEP or value >= 1.0 > self._last:
            self._last = value
            self._emit(protocol.Progress(value=round(value, 4)))


def _check_disk(job: SeparationJob, source: audio_io.SourceAudio) -> None:
    base = job.out_dir
    probe = base
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    needed = folder.estimate_disk_bytes(
        n_stems=len(job.wanted) + (1 if job.dereverb_vocals else 0),
        duration_s=source.duration_s,
        samplerate=source.samplerate,
        channels=source.original_channels,
    )
    if free < needed:
        raise RuntimeError(
            f"Spazio su disco insufficiente: servono circa {needed // 1_000_000} MB "
            f"e ce ne sono {free // 1_000_000} MB. Libera spazio e riprova."
        )


def _get_backend(
    cache: BackendCache, name: str, model: str, device: str, quality_name: str
) -> Backend:
    key = (name, model, device, quality_name)
    if key not in cache:
        quality = effective_quality(quality_name, device)
        cache[key] = create_backend(name, model, device, quality)
    return cache[key]


def _run_pass_blocks(
    backend: Backend,
    work: np.ndarray,
    wanted: frozenset[StemKind],
    on_progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
) -> dict[StemKind, np.ndarray]:
    """Esegue una passata a blocchi (§5.7 regola 6) e ricompone con
    overlap-add complementare."""
    import torch

    total = work.shape[-1]
    blocks = audio_io.split_blocks(total, backend.samplerate)
    outputs: dict[StemKind, np.ndarray] = {}
    for index, block in enumerate(blocks):
        chunk = torch.from_numpy(np.ascontiguousarray(work[:, block.start : block.end]))

        def block_progress(value: float, _i: int = index, _n: int = len(blocks)) -> None:
            on_progress((_i + value) / _n)

        result = backend.separate(chunk, wanted, block_progress, should_cancel)
        for kind, tensor in result.items():
            if kind not in outputs:
                outputs[kind] = np.zeros((tensor.shape[0], total), dtype=np.float32)
            audio_io.overlap_add(outputs[kind], tensor.numpy(), block)
    return outputs


def _first_stage_wanted(p: Pass, backend: Backend) -> frozenset[StemKind]:
    if p.mode == "full":
        # Insieme completo (§5.1.1 in `best`): tutte le sorgenti del
        # modello, così ogni sotto-modello del bag viene eseguito.
        return frozenset(backend.provides)
    return frozenset(p.needed)


def _run_second_stage(
    p: Pass,
    backends: BackendCache,
    job: SeparationJob,
    device: str,
    stage1: dict[StemKind, np.ndarray],
    stems: dict[StemKind, np.ndarray],
    wet_vocals: dict[str, np.ndarray],
    warnings: list[str],
    unavailable: list[Pass],
    on_progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
) -> None:
    assert p.input_stem is not None
    source = stems.get(p.input_stem, stage1.get(p.input_stem))
    if source is None:
        warnings.append(f"{p.label}: stem di ingresso mancante, passata saltata")
        unavailable.append(p)
        return
    try:
        backend = _get_backend(backends, p.backend, p.model, device, job.quality)
    except BackendUnavailable as exc:
        # §5.2.4: lo stem base sopravvive, avviso non bloccante.
        warnings.append(str(exc))
        unavailable.append(p)
        return
    result = _run_pass_blocks(
        backend, source, frozenset(p.needed), on_progress, should_cancel
    )
    if p.backend == "dereverb":
        wet_vocals["wet"] = source
        stems[StemKind.VOCALS] = result[StemKind.VOCALS]
        return
    if p.backend == "vocalsplit":
        lead = result[StemKind.LEAD_VOCALS]
        stems[StemKind.LEAD_VOCALS] = lead
        # backing per sottrazione: esatta, l'invariante regge (§5.2.2).
        stems[StemKind.BACKING_VOCALS] = source - lead
        return
    stems.update(result)


@dataclass
class _JobState:
    stage1: dict[StemKind, np.ndarray] = field(default_factory=dict)
    stems: dict[StemKind, np.ndarray] = field(default_factory=dict)
    wet_vocals: dict[str, np.ndarray] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unavailable: list[Pass] = field(default_factory=list)


def _execute_passes(
    job: SeparationJob,
    plan_: Plan,
    work: np.ndarray,
    device: str,
    backends: BackendCache,
    progress: _Progress,
    state: _JobState,
    duration_s: float,
    emit: Emit,
    should_cancel: Callable[[], bool],
) -> None:
    for index, p in enumerate(plan_.passes):
        emit(protocol.Phase(
            label=f"{p.label} — passata {index + 1} di {len(plan_.passes)}",
            pass_index=index + 1,
            pass_count=len(plan_.passes),
        ))
        started = time.perf_counter()
        if p.backend == "demucs4":
            backend = _get_backend(backends, p.backend, p.model, device, job.quality)
            wanted = _first_stage_wanted(p, backend)
            state.stage1 = _run_pass_blocks(
                backend, work, wanted, progress.pass_callback(index), should_cancel
            )
            state.stems.update(state.stage1)
        else:
            _run_second_stage(
                p, backends, job, device, state.stage1, state.stems,
                state.wet_vocals, state.warnings, state.unavailable,
                progress.pass_callback(index), should_cancel,
            )
        elapsed = time.perf_counter() - started
        if p not in state.unavailable:
            factors = demucs_factors(job.quality) if p.backend == "demucs4" else 1.0
            calibrate.record_measurement(
                p.rate_key, elapsed / (p.units * factors), duration_s
            )
        progress.complete_pass(index)


def run_job(
    job: SeparationJob,
    emit: Emit,
    should_cancel: Callable[[], bool] = lambda: False,
    backends: BackendCache | None = None,
) -> JobResult:
    backends = backends if backends is not None else {}
    source = audio_io.load(job.source)
    _check_disk(job, source)
    device = resolve_device(job.device)
    plan_ = plan(job)
    rates = calibrate.load_rates()
    weights = [
        estimate_pass_seconds(p, source.duration_s, rates, job.quality)
        for p in plan_.passes
    ]
    progress = _Progress(emit, weights)
    out_dir = folder.allocate_out_dir(job.out_dir, job.source.name)
    emit(protocol.Started(out_dir=str(out_dir)))

    work = audio_io.resample(source.data, source.samplerate, audio_io.MODEL_SAMPLERATE)
    state = _JobState()
    _execute_passes(
        job, plan_, work, device, backends, progress, state,
        source.duration_s, emit, should_cancel,
    )
    write = assemble.effective_write(job, state.unavailable)
    outputs = assemble.assemble_outputs(write, source, state.stage1, state.stems)
    result = assemble.write_all(
        job, write, source, out_dir, outputs, state.wet_vocals.get("wet"),
        plan_, state.warnings, emit,
    )
    for message in result.warnings:
        emit(protocol.Warning_(message=message))
    emit(protocol.Done(out_dir=str(result.out_dir), manifest=str(result.out_dir / "manifest.json")))
    return result


