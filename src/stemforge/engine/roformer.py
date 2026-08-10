"""Backend RoFormer (milestone M4).

BUILD_SPEC §5.8, §12-M4. Il checkpoint si sceglie all'apertura di M4 con
un A/B in cieco contro htdemucs_ft e la licenza si registra per
iscritto; i pesi si fissano con URL immutabile + SHA-256. Fino ad
allora questo backend non è selezionabile: dichiararlo qui, e non
nasconderlo, tiene il registro (registry.py) e il contratto già pronti.
"""

from __future__ import annotations

from stemforge.engine.contract import BackendUnavailable, Quality


class RoFormerBackend:
    name = "roformer"
    samplerate = 44100

    def __init__(self, device: str, quality: Quality) -> None:
        raise BackendUnavailable(
            "Il backend RoFormer arriva con la milestone M4: "
            "checkpoint e licenza non sono ancora stati adottati (§5.8)."
        )
