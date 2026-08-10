"""Secondo stadio: batteria -> kick / snare / toms / hihat / cymbals.

BUILD_SPEC §5.2.1, §5.8. Il modello concreto si sceglie all'apertura di
M6 con un A/B su brani reali (candidati: DrumSep / LarsNet), e i pesi si
fissano con URL immutabile + SHA-256. Finché quella scelta non è
verbalizzata, questo backend dichiara l'indisponibilità in modo onesto:
per §5.2.4 lo stem base sopravvive e l'utente riceve `drums.wav` con un
avviso non bloccante, mai un errore.

Il contratto e il posto nel piano sono già definitivi: adottare il
modello a M6 significa riempire `_load`, niente altro cambia.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from stemforge.engine.contract import BackendUnavailable, Quality
from stemforge.engine.demucs4 import models_dir
from stemforge.model.stem import StemKind

if TYPE_CHECKING:
    from torch import Tensor

WEIGHTS_FILENAME = "drumsplit.ckpt"  # fissato a M6 insieme allo SHA-256
WEIGHTS_SHA256: str | None = None  # None = modello non ancora adottato (§5.8)


class DrumSplitBackend:
    name = "drumsplit"
    samplerate = 44100
    provides = frozenset(
        {StemKind.KICK, StemKind.SNARE, StemKind.TOMS, StemKind.HIHAT, StemKind.CYMBALS}
    )

    def __init__(self, device: str, quality: Quality) -> None:
        self.device = device
        self.quality = quality
        self._model = self._load()

    def _load(self):
        weights = models_dir() / WEIGHTS_FILENAME
        if WEIGHTS_SHA256 is None or not weights.exists():
            raise BackendUnavailable(
                "Il dettaglio batteria non è ancora disponibile in questa "
                "versione: ottieni comunque lo stem batteria completo."
            )
        raise NotImplementedError("adozione modello: milestone M6")

    def separate(
        self,
        audio: "Tensor",
        wanted: frozenset[StemKind],
        on_progress: Callable[[float], None],
        should_cancel: Callable[[], bool],
    ) -> dict[StemKind, "Tensor"]:
        raise NotImplementedError("adozione modello: milestone M6")
