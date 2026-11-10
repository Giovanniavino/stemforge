"""Downmix multicanale -> stereo, ITU-R BS.775 (BUILD_SPEC §5.7 regola 7).

I modelli sono stereo. Tenere i primi due canali di un 5.1 butterebbe
via il centro, cioè la voce: si somma invece ogni canale nel lato
giusto, con centro e surround a -3 dB e LFE escluso. Nessuna
normalizzazione (regola 5): un eventuale clipping oltre 0 dBFS nei
float si conserva, e l'invariante di ricostruzione (§10.2) si misura
rispetto a QUESTO downmix.

L'ordine dei canali è quello standard WAV/SMPTE (lo stesso di FFmpeg per
i layout canonici): L R C LFE Ls Rs [Lb Rb]. Per 4 canali vale il quad
L R Ls Rs, la maschera di default di WAVE_FORMAT_EXTENSIBLE.
"""

from __future__ import annotations

import numpy as np

MINUS_3_DB = float(np.sqrt(0.5))  # 0.7071: centro e surround (BS.775)

# Contributo di ogni ruolo al canale (sinistro, destro).
_GAINS: dict[str, tuple[float, float]] = {
    "L": (1.0, 0.0),
    "R": (0.0, 1.0),
    "C": (MINUS_3_DB, MINUS_3_DB),
    "LFE": (0.0, 0.0),  # escluso: i modelli non lo sanno trattare, e in stereo non c'è
    "Ls": (MINUS_3_DB, 0.0),
    "Rs": (0.0, MINUS_3_DB),
    "Cs": (MINUS_3_DB, MINUS_3_DB),  # surround posteriore unico (6.1): -3 dB su entrambi
}

# Layout per numero di canali (ordine WAV/SMPTE).
LAYOUTS: dict[int, tuple[str, ...]] = {
    3: ("L", "R", "C"),
    4: ("L", "R", "Ls", "Rs"),
    5: ("L", "R", "C", "Ls", "Rs"),
    6: ("L", "R", "C", "LFE", "Ls", "Rs"),
    7: ("L", "R", "C", "LFE", "Cs", "Ls", "Rs"),
    8: ("L", "R", "C", "LFE", "Ls", "Rs", "Ls", "Rs"),
}

MAX_CHANNELS = max(LAYOUTS)


def matrix(channels: int) -> np.ndarray:
    """Matrice [2, channels] del downmix; KeyError per layout sconosciuti."""
    roles = LAYOUTS[channels]
    return np.array([[_GAINS[r][side] for r in roles] for side in (0, 1)], dtype=np.float64)


def to_stereo(audio: np.ndarray) -> np.ndarray:
    """[channels, samples] multicanale -> [2, samples] float32."""
    weights = matrix(audio.shape[0]).astype(np.float32)
    return np.ascontiguousarray(weights @ audio, dtype=np.float32)
