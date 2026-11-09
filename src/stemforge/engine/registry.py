"""Registro nome -> costruttore di backend.

BUILD_SPEC §3, D4. Il worker chiede i backend per nome (dal piano);
i moduli concreti restano isolati e intercambiabili. I costruttori sono
pigri: un backend di 2° stadio senza pesi non impedisce il 1° (§5.2.4).
"""

from __future__ import annotations

import importlib
from typing import Callable

from stemforge.engine.contract import Backend, BackendUnavailable, Quality


def _make_demucs(model_name: str, device: str, quality: Quality) -> Backend:
    from stemforge.engine.demucs4 import Demucs4Backend

    return Demucs4Backend(model_name, device, quality)


def _make_drumsplit(model_name: str, device: str, quality: Quality) -> Backend:
    from stemforge.engine.drumsplit import DrumSplitBackend

    return DrumSplitBackend(device, quality)


def _make_vocalsplit(model_name: str, device: str, quality: Quality) -> Backend:
    from stemforge.engine.vocalsplit import VocalSplitBackend

    return VocalSplitBackend(device, quality)


def _make_dereverb(model_name: str, device: str, quality: Quality) -> Backend:
    from stemforge.engine.dereverb import DereverbBackend

    return DereverbBackend(device, quality)


_FACTORIES: dict[str, Callable[[str, str, Quality], Backend]] = {
    "demucs4": _make_demucs,
    "drumsplit": _make_drumsplit,
    "vocalsplit": _make_vocalsplit,
    "dereverb": _make_dereverb,
}


def is_available(backend_name: str) -> bool:
    """Il modello di questo backend è adottato in questa versione?

    Per i derivati il segnale è WEIGHTS_SHA256: finché è None il modello
    non è stato scelto (§5.8) e il backend dichiarerebbe sempre
    BackendUnavailable. Nessun import di torch: lo chiama l'UI a ogni avvio.
    """
    if backend_name == "demucs4":
        return True
    if backend_name not in ("drumsplit", "vocalsplit", "dereverb"):
        return False
    module = importlib.import_module(f"stemforge.engine.{backend_name}")
    return getattr(module, "WEIGHTS_SHA256", None) is not None


def create_backend(
    backend_name: str, model_name: str, device: str, quality: Quality
) -> Backend:
    factory = _FACTORIES.get(backend_name)
    if factory is None:
        raise BackendUnavailable(f"backend sconosciuto: {backend_name}")
    return factory(model_name, device, quality)
