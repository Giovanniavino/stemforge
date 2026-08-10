"""StemKind e StemSpec: il vocabolario degli stem e il grafo delle dipendenze.

BUILD_SPEC §4.1. Questo modulo è la fonte unica di verità su quali stem
esistono, quali sono base e quali derivati, e da cosa deriva ognuno.
Il pianificatore (engine/planner.py) legge solo da qui.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StemKind(StrEnum):
    # base — primo stadio (§5.1)
    VOCALS = "vocals"
    DRUMS = "drums"
    BASS = "bass"
    GUITAR = "guitar"
    PIANO = "piano"
    OTHER = "other"
    INSTRUMENTAL = "instrumental"  # mix meno vocals, per sottrazione

    # derivati da DRUMS — secondo stadio
    KICK = "kick"
    SNARE = "snare"
    TOMS = "toms"
    HIHAT = "hihat"
    CYMBALS = "cymbals"

    # derivati da VOCALS — secondo stadio
    LEAD_VOCALS = "lead_vocals"
    BACKING_VOCALS = "backing_vocals"


@dataclass(frozen=True)
class StemSpec:
    kind: StemKind
    stage: int  # 1 = base, 2 = derivato
    derives_from: StemKind | None  # None per i base
    label: str  # nome mostrato nell'UI


SPECS: dict[StemKind, StemSpec] = {
    spec.kind: spec
    for spec in (
        StemSpec(StemKind.VOCALS, 1, None, "Voce"),
        StemSpec(StemKind.DRUMS, 1, None, "Batteria"),
        StemSpec(StemKind.BASS, 1, None, "Basso"),
        StemSpec(StemKind.GUITAR, 1, None, "Chitarra"),
        StemSpec(StemKind.PIANO, 1, None, "Piano"),
        StemSpec(StemKind.OTHER, 1, None, "Altro"),
        StemSpec(StemKind.INSTRUMENTAL, 1, None, "Strumentale"),
        StemSpec(StemKind.KICK, 2, StemKind.DRUMS, "Kick"),
        StemSpec(StemKind.SNARE, 2, StemKind.DRUMS, "Snare"),
        StemSpec(StemKind.TOMS, 2, StemKind.DRUMS, "Toms"),
        StemSpec(StemKind.HIHAT, 2, StemKind.DRUMS, "Hi-hat"),
        StemSpec(StemKind.CYMBALS, 2, StemKind.DRUMS, "Cymbals"),
        StemSpec(StemKind.LEAD_VOCALS, 2, StemKind.VOCALS, "Lead"),
        StemSpec(StemKind.BACKING_VOCALS, 2, StemKind.VOCALS, "Cori"),
    )
}

# Sorgenti "concrete" del primo stadio: quelle che un modello sa produrre
# per inferenza. OTHER e INSTRUMENTAL non sono qui perché nel piano si
# ottengono per sottrazione dal mix (§5.1.1), tranne il caso OTHER-solo.
CONCRETE_BASE: frozenset[StemKind] = frozenset(
    {StemKind.VOCALS, StemKind.DRUMS, StemKind.BASS, StemKind.GUITAR, StemKind.PIANO}
)

# Le quattro sorgenti di htdemucs_ft, nell'ordine del modello.
FT_SOURCES: tuple[StemKind, ...] = (
    StemKind.DRUMS,
    StemKind.BASS,
    StemKind.OTHER,
    StemKind.VOCALS,
)

# Le sei sorgenti di htdemucs_6s, nell'ordine del modello.
SIX_SOURCES: tuple[StemKind, ...] = (
    StemKind.DRUMS,
    StemKind.BASS,
    StemKind.OTHER,
    StemKind.VOCALS,
    StemKind.GUITAR,
    StemKind.PIANO,
)


def derived_of(base: StemKind) -> frozenset[StemKind]:
    """Tutti i derivati di uno stem base."""
    return frozenset(k for k, s in SPECS.items() if s.derives_from == base)


def is_derived(kind: StemKind) -> bool:
    return SPECS[kind].stage == 2
