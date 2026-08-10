"""Il pianificatore: da "cosa vuole l'utente" a "quali passate eseguire".

BUILD_SPEC §5.3. È il pezzo di logica con più casi limite del progetto,
gira senza torch e va coperto da test esaustivi (§10.3).

Decisioni incorporate qui, con la ragione:

- `other` e `instrumental` si ottengono SEMPRE per sottrazione dal mix
  (§5.1.1): l'invariante di ricostruzione (§10.2) regge per costruzione,
  non per bontà del modello. Unica eccezione: `other` richiesto da solo,
  dove non c'è nulla da sottrarre e si usa il sotto-modello dedicato.
- Il piano dichiara le SORGENTI necessarie, non gli indici dei
  sotto-modelli: è il backend (demucs4.py) a leggere i pesi reali del
  bag e a decidere quali sotto-modelli servono. Così l'esecuzione
  parziale resta identica all'insieme completo anche se i pesi non
  fossero one-hot.
- In `best` il primo stadio è sempre l'insieme completo (§5.1.1):
  nessuna scorciatoia, per scelta del committente.
- Ordine del 2° stadio: de-riverbero PRIMA dello split lead/cori, così
  lo split lavora sulla voce asciutta, che è l'ingresso più facile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from stemforge.engine.contract import PRESETS
from stemforge.model.job import SeparationJob
from stemforge.model.stem import CONCRETE_BASE, SPECS, StemKind, is_derived

MODEL_FT = "htdemucs_ft"
MODEL_6S = "htdemucs_6s"

# Costi di riferimento pre-calibrazione: secondi di calcolo per secondo
# di audio, misurati grossolanamente su CPU x86. La calibrazione al primo
# avvio (§8.2.1) li sostituisce con i valori della macchina reale.
DEFAULT_RATES: dict[str, float] = {
    "demucs4/htdemucs_ft/sub": 0.9,  # un sotto-modello del bag
    "demucs4/htdemucs_6s/full": 3.2,  # modello singolo a sei uscite
    "drumsplit": 0.7,
    "vocalsplit": 0.7,
    "dereverb": 0.5,
}

# La baseline di calibrazione è misurata a overlap 0.10 e shifts 0
# (preset `balanced`): i fattori di scala partono da lì.
_BASELINE_OVERLAP = 0.10


@dataclass(frozen=True)
class Pass:
    backend: str  # "demucs4" | "drumsplit" | "vocalsplit" | "dereverb"
    model: str  # nome del modello di primo stadio, o == backend per il 2°
    input_stem: StemKind | None  # None = il mix
    needed: tuple[StemKind, ...]  # sorgenti che questa passata deve produrre
    mode: str  # "partial" | "full" (solo demucs4 distingue)
    rate_key: str  # voce della tabella di calibrazione
    units: float  # multipli del costo unitario (es. n. sotto-modelli)
    label: str  # fase mostrata in §8.3


@dataclass(frozen=True)
class Plan:
    passes: tuple[Pass, ...]
    write: tuple[StemKind, ...]  # cosa finisce su disco, ordine stabile
    first_stage_model: str
    dereverb: bool
    quality: str


def _first_stage_sources(job: SeparationJob) -> tuple[set[StemKind], bool]:
    """Sorgenti concrete da inferire e se serve il modello a 6 uscite."""
    wanted = set(job.wanted)
    targets = wanted & CONCRETE_BASE
    for kind in wanted:
        if is_derived(kind):
            base = SPECS[kind].derives_from
            assert base is not None
            targets.add(base)
    if StemKind.INSTRUMENTAL in wanted or job.dereverb_vocals:
        targets.add(StemKind.VOCALS)
    needs_6s = bool(targets & {StemKind.GUITAR, StemKind.PIANO})
    return targets, needs_6s


def _first_stage_pass(job: SeparationJob, targets: set[StemKind], needs_6s: bool) -> Pass:
    if needs_6s:
        # §5.1.1 non si applica: htdemucs_6s è un modello singolo.
        return Pass(
            backend="demucs4",
            model=MODEL_6S,
            input_stem=None,
            needed=tuple(sorted(targets)),
            mode="full",
            rate_key="demucs4/htdemucs_6s/full",
            units=1.0,
            label="Separazione",
        )
    full = job.quality == "best" or not targets
    if not targets:
        # `other` da solo: niente da sottrarre, si usa il sotto-modello
        # dedicato. In `best` comunque l'insieme completo.
        needed: tuple[StemKind, ...] = (StemKind.OTHER,)
        mode = "full" if job.quality == "best" else "partial"
        units = 4.0 if mode == "full" else 1.0
    elif full:
        needed = tuple(sorted(targets))
        mode = "full"
        units = 4.0
    else:
        needed = tuple(sorted(targets))
        mode = "partial"
        units = float(len(needed))
    return Pass(
        backend="demucs4",
        model=MODEL_FT,
        input_stem=None,
        needed=needed,
        mode=mode,
        rate_key="demucs4/htdemucs_ft/sub",
        units=units,
        label="Separazione",
    )


def _second_stage_passes(job: SeparationJob) -> tuple[Pass, ...]:
    wanted = set(job.wanted)
    passes: list[Pass] = []
    drum_derived = tuple(sorted(k for k in wanted if SPECS[k].derives_from == StemKind.DRUMS))
    if drum_derived:
        passes.append(
            Pass(
                backend="drumsplit",
                model="drumsplit",
                input_stem=StemKind.DRUMS,
                needed=drum_derived,
                mode="full",
                rate_key="drumsplit",
                units=1.0,
                label="Dettaglio batteria",
            )
        )
    if job.dereverb_vocals:
        passes.append(
            Pass(
                backend="dereverb",
                model="dereverb",
                input_stem=StemKind.VOCALS,
                needed=(StemKind.VOCALS,),
                mode="full",
                rate_key="dereverb",
                units=1.0,
                label="De-riverbero voce",
            )
        )
    vocal_derived = tuple(sorted(k for k in wanted if SPECS[k].derives_from == StemKind.VOCALS))
    if vocal_derived:
        passes.append(
            Pass(
                backend="vocalsplit",
                model="vocalsplit",
                input_stem=StemKind.VOCALS,
                needed=vocal_derived,
                mode="full",
                rate_key="vocalsplit",
                units=1.0,
                label="Dettaglio voce",
            )
        )
    return tuple(passes)


def plan(job: SeparationJob) -> Plan:
    targets, needs_6s = _first_stage_sources(job)
    first = _first_stage_pass(job, targets, needs_6s)
    second = _second_stage_passes(job)
    return Plan(
        passes=(first, *second),
        write=tuple(job.wanted),
        first_stage_model=first.model,
        dereverb=job.dereverb_vocals,
        quality=job.quality,
    )


def subtraction_terms(write: tuple[StemKind, ...]) -> tuple[StemKind, ...]:
    """Cosa sottrarre dal mix per ottenere `other` senza doppi conteggi.

    Regola di copertura: per ogni famiglia si sottrae lo stem base se è
    scritto, altrimenti i suoi derivati scritti (che sono contenuti nel
    base). Mai entrambi: kick è già dentro drums.
    """
    written = set(write)
    terms: list[StemKind] = []
    for kind in write:
        if kind in (StemKind.OTHER, StemKind.INSTRUMENTAL):
            continue
        if is_derived(kind):
            base = SPECS[kind].derives_from
            if base in written:
                continue  # coperto dal base
        terms.append(kind)
    return tuple(terms)


def demucs_factors(quality: str) -> float:
    """Scala il costo del 1° stadio rispetto alla baseline di calibrazione.

    Il numero di segmenti cresce come 1/(1-overlap); ogni shift è
    un'inferenza completa in più (§5.6).
    """
    preset = PRESETS[quality]
    overlap_factor = (1.0 - _BASELINE_OVERLAP) / (1.0 - preset.overlap)
    return overlap_factor * (1.0 + preset.shifts)


def estimate_pass_seconds(
    p: Pass, duration_s: float, rates: Mapping[str, float], quality: str
) -> float:
    rate = rates.get(p.rate_key, DEFAULT_RATES[p.rate_key])
    seconds = duration_s * rate * p.units
    if p.backend == "demucs4":
        seconds *= demucs_factors(quality)
    return seconds


def estimate_seconds(plan_: Plan, duration_s: float, rates: Mapping[str, float]) -> float:
    """Somma dei costi delle passate. Il margine del 15% (§8.2.1) lo
    applica chi mostra la stima, non il pianificatore."""
    return sum(
        estimate_pass_seconds(p, duration_s, rates, plan_.quality) for p in plan_.passes
    )
