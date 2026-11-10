"""Le passate di un job: 1° stadio con ripiego su CPU, 2° stadio, blocchi.

BUILD_SPEC §5.1.1, §5.2.4, §5.7 regola 6, §6.1, D8. Staccato da
pipeline.py, che resta l'orchestrazione: qui c'è come si esegue UNA
passata.

- Ogni passata va a blocchi (engine/blocks.py), con la lunghezza che
  la RAM disponibile IN QUEL MOMENTO consente: il modello è già
  caricato e gli array del brano già allocati, quindi la lettura è
  quella che conta.
- Un acceleratore (MPS, CUDA) che fallisce durante un job: la passata
  si rifà sulla CPU con un avviso (D8). Un errore di calcolo spegne
  l'acceleratore per i job successivi; una memoria esaurita no, è
  contingente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from stemforge.engine import blocks, device
from stemforge.engine.contract import Backend, BackendUnavailable, CancelledError, effective_quality
from stemforge.engine.errors import is_memory_error
from stemforge.engine.planner import Pass
from stemforge.engine.registry import create_backend
from stemforge.model.stem import StemKind
from stemforge.worker.i18n import t

log = logging.getLogger(__name__)

BackendCache = dict[tuple[str, str, str, str], Backend]
MemoryProbe = Callable[[], "int | None"]


@dataclass
class JobState:
    device: str
    available_memory: MemoryProbe = device.available_memory_bytes
    stage1: dict[StemKind, np.ndarray] = field(default_factory=dict)
    stems: dict[StemKind, np.ndarray] = field(default_factory=dict)
    wet_vocals: dict[str, np.ndarray] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    unavailable: list[Pass] = field(default_factory=list)


def get_backend(
    cache: BackendCache, name: str, model: str, device_name: str, quality_name: str
) -> Backend:
    key = (name, model, device_name, quality_name)
    if key not in cache:
        quality = effective_quality(quality_name, device_name)
        cache[key] = create_backend(name, model, device_name, quality)
    return cache[key]


def run_pass_blocks(
    backend: Backend,
    work: np.ndarray,
    wanted: frozenset[StemKind],
    on_progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
    available_memory: MemoryProbe,
) -> dict[StemKind, np.ndarray]:
    """Esegue una passata a blocchi e ricompone con overlap-add complementare."""
    import torch

    total = work.shape[-1]
    parts = blocks.split_blocks(total, backend.samplerate, available_memory())
    outputs: dict[StemKind, np.ndarray] = {}
    for index, block in enumerate(parts):
        chunk = torch.from_numpy(np.ascontiguousarray(work[:, block.start : block.end]))

        def block_progress(value: float, _i: int = index, _n: int = len(parts)) -> None:
            on_progress((_i + value) / _n)

        result = backend.separate(chunk, wanted, block_progress, should_cancel)
        for kind, tensor in result.items():
            if kind not in outputs:
                outputs[kind] = np.zeros((tensor.shape[0], total), dtype=np.float32)
            blocks.overlap_add(outputs[kind], tensor.numpy(), block)
    return outputs


def _first_stage_wanted(p: Pass, backend: Backend) -> frozenset[StemKind]:
    if p.mode == "full":
        # Insieme completo (§5.1.1 in `best`): tutte le sorgenti del
        # modello, così ogni sotto-modello del bag viene eseguito.
        return frozenset(backend.provides)
    return frozenset(p.needed)


def run_first_stage(
    quality: str,
    p: Pass,
    work: np.ndarray,
    backends: BackendCache,
    state: JobState,
    on_progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
) -> None:
    """1° stadio, con ripiego su CPU se l'acceleratore fallisce (D8)."""

    def run_on(device_name: str) -> None:
        backend = get_backend(backends, p.backend, p.model, device_name, quality)
        wanted = _first_stage_wanted(p, backend)
        state.stage1 = run_pass_blocks(
            backend, work, wanted, on_progress, should_cancel, state.available_memory
        )

    try:
        run_on(state.device)
    except (CancelledError, BackendUnavailable):
        raise
    except Exception as exc:
        if state.device not in device.ACCELERATORS:
            raise
        log.warning("%s fallito, ripiego su CPU", state.device, exc_info=True)
        if not is_memory_error(exc):
            device.save_verdict(state.device, False, f"errore durante un job: {exc!r}")
        state.warnings.append(t("warn.accel_fallback", device=state.device.upper()))
        state.device = "cpu"
        run_on("cpu")
    state.stems.update(state.stage1)


def _second_stage_backend(p: Pass, backends: BackendCache, quality: str,
                          state: JobState) -> Backend | None:
    try:
        return get_backend(backends, p.backend, p.model, state.device, quality)
    except BackendUnavailable:
        # §5.2.4: lo stem base sopravvive, avviso non bloccante.
        log.info("2° stadio %s non disponibile", p.backend, exc_info=True)
        state.warnings.append(t(f"warn.unavailable.{p.backend}"))
        state.unavailable.append(p)
        return None


def run_second_stage(
    p: Pass,
    backends: BackendCache,
    quality: str,
    state: JobState,
    on_progress: Callable[[float], None],
    should_cancel: Callable[[], bool],
) -> None:
    assert p.input_stem is not None
    source = state.stems.get(p.input_stem, state.stage1.get(p.input_stem))
    if source is None:
        state.warnings.append(t("warn.missing_input", label=t(f"phase.{p.backend}")))
        state.unavailable.append(p)
        return
    backend = _second_stage_backend(p, backends, quality, state)
    if backend is None:
        return
    result = run_pass_blocks(
        backend, source, frozenset(p.needed), on_progress, should_cancel, state.available_memory
    )
    if p.backend == "dereverb":
        state.wet_vocals["wet"] = source
        state.stems[StemKind.VOCALS] = result[StemKind.VOCALS]
        return
    if p.backend == "vocalsplit":
        lead = result[StemKind.LEAD_VOCALS]
        state.stems[StemKind.LEAD_VOCALS] = lead
        # backing per sottrazione: esatta, l'invariante regge (§5.2.2).
        state.stems[StemKind.BACKING_VOCALS] = source - lead
        return
    state.stems.update(result)
