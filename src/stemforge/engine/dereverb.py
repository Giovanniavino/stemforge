"""Secondo stadio: de-riverbero della voce.

BUILD_SPEC §5.2.3, §5.8. Non produce uno stem: trasforma `vocals` nella
versione asciutta; il chiamante scrive anche `vocals_wet` con
l'originale. È l'unica cosa della spec autorizzata a rompere
l'invariante di ricostruzione, e il manifest lo dichiara.

Modello da adottare a M6 (candidato: famiglia De-Echo/De-Reverb UVR),
con licenza verificata e pesi fissati. Fino ad allora: indisponibile in
modo onesto, la voce resta com'è (§5.2.4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from stemforge.engine.contract import BackendUnavailable, Quality
from stemforge.engine.demucs4 import models_dir
from stemforge.model.stem import StemKind

if TYPE_CHECKING:
    from torch import Tensor

WEIGHTS_FILENAME = "dereverb.ckpt"
WEIGHTS_SHA256: str | None = None  # None = modello non ancora adottato (§5.8)


class DereverbBackend:
    name = "dereverb"
    samplerate = 44100
    provides = frozenset({StemKind.VOCALS})

    def __init__(self, device: str, quality: Quality) -> None:
        self.device = device
        self.quality = quality
        self._model = self._load()

    def _load(self):
        weights = models_dir() / WEIGHTS_FILENAME
        if WEIGHTS_SHA256 is None or not weights.exists():
            raise BackendUnavailable(
                "Il de-riverbero non è ancora disponibile in questa versione: "
                "la voce resta con il riverbero originale."
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
