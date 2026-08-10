"""Secondo stadio: voce -> lead / cori.

BUILD_SPEC §5.2.2, §5.8. Come drumsplit: il modello karaoke si adotta a
M6 con A/B e pesi fissati; fino ad allora il backend è onestamente
indisponibile e lo stem `vocals` sopravvive (§5.2.4).

Quando il modello ci sarà: produce LEAD_VOCALS, e BACKING_VOCALS si
ricava per sottrazione (vocals - lead), esatta per costruzione, così
l'invariante §10.2 regge anche a questo livello dell'albero.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from stemforge.engine.contract import BackendUnavailable, Quality
from stemforge.engine.demucs4 import models_dir
from stemforge.model.stem import StemKind

if TYPE_CHECKING:
    from torch import Tensor

WEIGHTS_FILENAME = "vocalsplit.ckpt"
WEIGHTS_SHA256: str | None = None  # None = modello non ancora adottato (§5.8)


class VocalSplitBackend:
    name = "vocalsplit"
    samplerate = 44100
    provides = frozenset({StemKind.LEAD_VOCALS, StemKind.BACKING_VOCALS})

    def __init__(self, device: str, quality: Quality) -> None:
        self.device = device
        self.quality = quality
        self._model = self._load()

    def _load(self):
        weights = models_dir() / WEIGHTS_FILENAME
        if WEIGHTS_SHA256 is None or not weights.exists():
            raise BackendUnavailable(
                "La separazione lead/cori non è ancora disponibile in questa "
                "versione: ottieni comunque lo stem voce completo."
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
