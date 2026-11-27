"""La pipeline di esecuzione di un SeparationJob.

BUILD_SPEC D2, §5.3, §8.3. Serve sia il worker (runner.py) che la CLI:
run_job è l'unico punto in cui piano, backend ed export si incontrano.
Come si esegue una singola passata sta in passes.py, i controlli
preliminari in preflight.py, l'assemblaggio in assemble.py.

Decisioni non ovvie, con la ragione:
- La cartella di output si alloca PRIMA dell'inferenza e si annuncia
  con `Started`: se l'utente annulla, il padre sa cosa ripulire.
- `other` e `instrumental` si calcolano per sottrazione AL SAMPLE RATE
  ORIGINALE, dal mix originale: così l'invariante di ricostruzione
  (§10.2) regge esattamente anche dopo il round-trip di resampling.
- Con de-riverbero attivo la sottrazione usa la voce WET (l'uscita vera
  del 1° stadio): il riverbero rimosso non deve finire dentro `other`.
- Ogni testo per l'utente (fasi, avvisi) esce nella lingua del processo
  (worker/i18n.py, §8.6).
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np

from stemforge.engine import audio_io, calibrate
from stemforge.engine.planner import Plan, demucs_factors, estimate_pass_seconds, plan
from stemforge.export import folder
from stemforge.model.job import JobResult, SeparationJob
from stemforge.worker import assemble, preflight, protocol
from stemforge.worker.i18n import t
from stemforge.worker.passes import (
    BackendCache,
    JobState,
    MemoryProbe,
    run_first_stage,
    run_second_stage,
)

__all__ = ["BackendCache", "run_job"]

Emit = Callable[[protocol.Message], None]

_MIN_PROGRESS_STEP = 0.005


class _Progress:
    """Avanzamento globale = somma pesata dei costi delle passate (§8.3),
    monotòno per costruzione."""

    def __init__(self, emit: Emit, weights: list[float]) -> None:
        total = sum(weights) or 1.0
        self._fractions = [w / total for w in weights]
        self._emit = emit
        self._last = -1.0

    def pass_callback(self, pass_index: int) -> Callable[[float], None]:
        base = sum(self._fractions[:pass_index])
        weight = self._fractions[pass_index]

        def callback(value: float) -> None:
            self._report(base + weight * min(1.0, max(0.0, value)))

        return callback

    def complete_pass(self, pass_index: int) -> None:
        self._report(sum(self._fractions[: pass_index + 1]))

    def _report(self, value: float) -> None:
        value = max(self._last, value)
        if value - self._last >= _MIN_PROGRESS_STEP or value >= 1.0 > self._last:
            self._last = value
            self._emit(protocol.Progress(value=round(value, 4)))


def _execute_passes(
    job: SeparationJob,
    plan_: Plan,
    work: np.ndarray,
    backends: BackendCache,
    progress: _Progress,
    state: JobState,
    duration_s: float,
    emit: Emit,
    should_cancel: Callable[[], bool],
) -> None:
    count = len(plan_.passes)
    for index, p in enumerate(plan_.passes):
        label = t("phase.pass", label=t(f"phase.{p.backend}"), index=index + 1, count=count)
        emit(protocol.Phase(label=label, pass_index=index + 1, pass_count=count))
        started = time.perf_counter()
        callback = progress.pass_callback(index)
        if p.backend == "demucs4":
            run_first_stage(job.quality, p, work, backends, state, callback, should_cancel)
        else:
            run_second_stage(p, backends, job.quality, state, callback, should_cancel)
        elapsed = time.perf_counter() - started
        if p not in state.unavailable:
            factors = demucs_factors(job.quality) if p.backend == "demucs4" else 1.0
            calibrate.record_measurement(p.rate_key, elapsed / (p.units * factors), duration_s)
        progress.complete_pass(index)


def _job_device(job: SeparationJob, backends: BackendCache) -> str:
    """Device del job. Una cache pre-popolata (test, batch) fissa già il
    device dei backend: rispettarla evita di toccare torch per niente."""
    preset = {key[2] for key in backends}
    if job.device == "auto" and len(preset) == 1:
        return preset.pop()
    return calibrate.resolve_job_device(job.device)


def _new_state(job: SeparationJob, backends: BackendCache,
               available_memory: MemoryProbe | None) -> JobState:
    state = JobState(device=_job_device(job, backends))
    if available_memory is not None:
        state.available_memory = available_memory
    return state


def run_job(
    job: SeparationJob,
    emit: Emit,
    should_cancel: Callable[[], bool] = lambda: False,
    backends: BackendCache | None = None,
    available_memory: MemoryProbe | None = None,
) -> JobResult:
    """Esegue un job. `available_memory` sostituisce la lettura della RAM
    della macchina (test, §6.1); None = quella vera."""
    backends = backends if backends is not None else {}
    source = audio_io.load(job.source)
    preflight.check_disk(job, source)
    plan_ = plan(job)
    rates = calibrate.load_rates()
    weights = [estimate_pass_seconds(p, source.duration_s, rates, job.quality)
               for p in plan_.passes]
    progress = _Progress(emit, weights)
    out_dir = folder.allocate_out_dir(job.out_dir, job.source.name)
    emit(protocol.Started(out_dir=str(out_dir)))

    work = audio_io.resample(source.data, source.samplerate, audio_io.MODEL_SAMPLERATE)
    state = _new_state(job, backends, available_memory)
    if source.downmixed:
        state.warnings.append(
            t("warn.downmix", name=job.source.name, channels=source.source_channels)
        )
    _execute_passes(job, plan_, work, backends, progress, state,
                    source.duration_s, emit, should_cancel)
    write = assemble.effective_write(job, state.unavailable)
    outputs = assemble.assemble_outputs(write, source, state.stage1, state.stems)
    result = assemble.write_all(job, write, source, out_dir, outputs,
                                state.wet_vocals.get("wet"), plan_, state.warnings, emit)
    for message in result.warnings:
        emit(protocol.Warning_(message=message))
    emit(protocol.Done(out_dir=str(result.out_dir), manifest=str(result.out_dir / "manifest.json")))
    return result
