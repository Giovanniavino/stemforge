"""Risoluzione del device di calcolo.

BUILD_SPEC §4.2, D6. Il target (Mac Intel) è solo CPU; CUDA esiste per
il dev-box Windows. Non esiste il caso MPS. torch è importato in modo
pigro perché i test unitari girano senza.
"""

from __future__ import annotations

from typing import Callable


def _cuda_available() -> bool:
    import torch

    return bool(torch.cuda.is_available())


def resolve_device(
    requested: str, cuda_available: Callable[[], bool] = _cuda_available
) -> str:
    """Da "auto"/"cpu"/"cuda" al device effettivo.

    `cuda_available` è iniettabile per testare senza torch.
    """
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not cuda_available():
            raise RuntimeError(
                "CUDA richiesto ma non disponibile: usa --device cpu o auto"
            )
        return "cuda"
    if requested == "auto":
        return "cuda" if cuda_available() else "cpu"
    raise ValueError(f"device sconosciuto: {requested!r}")
