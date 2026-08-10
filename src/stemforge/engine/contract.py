"""Contratto Backend e preset di qualità.

BUILD_SPEC §5.5, §5.6. Il contratto è l'unica superficie fra il
pianificatore e le famiglie di modelli: cambiare modello non tocca
UI, export o data model (D4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

from stemforge.model.stem import StemKind

if TYPE_CHECKING:  # torch resta un import solo di tipo: i test girano senza
    from torch import Tensor


class BackendUnavailable(RuntimeError):
    """Il backend non può girare (pesi mancanti, licenza non fissata...).

    Per i derivati vale §5.2.4: lo stem base sopravvive, l'errore diventa
    un avviso non bloccante.
    """


class CancelledError(RuntimeError):
    """L'utente ha annullato: il chiamante ripulisce i parziali."""


@runtime_checkable
class Backend(Protocol):
    name: str
    provides: frozenset[StemKind]
    samplerate: int

    def separate(
        self,
        audio: "Tensor",  # [channels, samples] float32
        wanted: frozenset[StemKind],
        on_progress: Callable[[float], None],
        should_cancel: Callable[[], bool],
    ) -> dict[StemKind, "Tensor"]:
        """Separa. on_progress riceve 0.0-1.0 monotòno crescente.

        should_cancel va consultato fra un segmento e l'altro per la
        terminazione pulita; la garanzia del secondo la dà il kill del
        processo figlio (§5.5). Se should_cancel() è vero, sollevare
        CancelledError.
        """
        ...


@dataclass(frozen=True)
class Quality:
    overlap: float
    shifts: int
    half: bool  # solo CUDA; su CPU sempre False (§5.6)
    segment_s: float | None


# Il default è `best`: la qualità viene prima del tempo (priorità del
# committente, §0). `segment` resta 7.8 ovunque: alzarlo fa swappare
# gli 8 GB del target senza aggiungere qualità.
PRESETS: dict[str, Quality] = {
    "fast": Quality(overlap=0.05, shifts=0, half=True, segment_s=7.8),
    "balanced": Quality(overlap=0.10, shifts=0, half=True, segment_s=7.8),
    "best": Quality(overlap=0.25, shifts=2, half=False, segment_s=7.8),
}

DEFAULT_QUALITY = "best"


def effective_quality(preset: str, device: str) -> Quality:
    """Preset adattato al device: fp16 su CPU è emulato e più lento (§5.6)."""
    quality = PRESETS[preset]
    if device == "cpu" and quality.half:
        return Quality(
            overlap=quality.overlap,
            shifts=quality.shifts,
            half=False,
            segment_s=quality.segment_s,
        )
    return quality
