"""Ponte di sola logica fra UI e pianificatore.

BUILD_SPEC §8.2.1: la stima mostrata viene dal pianificatore, non da una
formula nell'UI. Ma i widget non importano engine (§8.5): questo modulo
sta nel livello worker (ui -> worker -> engine, §3) ed espone il minimo
indispensabile, senza torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stemforge.engine import calibrate
from stemforge.engine.planner import estimate_seconds, plan
from stemforge.model.job import SeparationJob

# Sovrastima del 15%: finire prima è un piacere, dopo è un difetto (§8.2.1).
ESTIMATE_MARGIN = 1.15

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif"}


@dataclass(frozen=True)
class DerivedOptions:
    """Quali opzioni di 2° stadio mostrare: solo quelle con un modello vero."""

    drum_detail: bool
    vocal_split: bool
    dereverb: bool


def derived_options() -> DerivedOptions:
    from stemforge.engine.registry import is_available

    return DerivedOptions(
        drum_detail=is_available("drumsplit"),
        vocal_split=is_available("vocalsplit"),
        dereverb=is_available("dereverb"),
    )


@dataclass(frozen=True)
class PlanSummary:
    seconds: float  # già col margine del 15%
    n_passes: int
    first_stage_model: str


def summarize(job: SeparationJob, duration_s: float) -> PlanSummary:
    plan_ = plan(job)
    rates = calibrate.load_rates()
    seconds = estimate_seconds(plan_, duration_s, rates) * ESTIMATE_MARGIN
    return PlanSummary(
        seconds=seconds,
        n_passes=len(plan_.passes),
        first_stage_model=plan_.first_stage_model,
    )


def probe_duration(path: Path) -> float | None:
    """Durata del file, o None se non leggibile. Vive qui e non nell'UI
    perché decodificare è lavoro del motore (vietato nei widget, §8.5)."""
    from stemforge.engine.audio_io import probe_duration as probe

    return probe(path)


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def prepared_marker() -> Path:
    """Il primo avvio è già stato fatto? (pesi scaricati + calibrazione)."""
    return calibrate.calibration_path().parent / "prepared.json"


def format_eta(seconds: float) -> str:
    """"~18 s", "~14 min", "~1 h 20 min": mai eufemismi (§8.2.1)."""
    if seconds < 90:
        return f"~{max(1, round(seconds))} s"
    minutes = seconds / 60
    if minutes < 90:
        return f"~{round(minutes)} min"
    hours = int(minutes // 60)
    rest = round(minutes - hours * 60)
    return f"~{hours} h {rest:02d} min"
