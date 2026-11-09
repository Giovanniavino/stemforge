"""Ambiente di esecuzione: device di calcolo, certificati, verdetto MPS.

BUILD_SPEC §4.2, §5.6, D6. Tre famiglie di macchine:

- Mac Intel e PC senza GPU NVIDIA: CPU.
- PC con GPU NVIDIA (solo sviluppo, build CUDA): CUDA.
- Mac Apple Silicon: MPS, la GPU integrata — 5-8x sulla CPU (§6.2).

MPS non si accende sulla fiducia: al primo uso un controllo confronta
l'uscita MPS con quella CPU sullo stesso audio (calibrate.validate_mps)
e il verdetto si salva in device.json. Senza verdetto positivo, "auto"
resta su CPU: la qualità viene prima del tempo (§0). torch è importato
in modo pigro perché i test unitari girano senza.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from stemforge.engine import paths


def ensure_ca_bundle() -> None:
    """Punta OpenSSL al bundle CA di certifi, se non già configurato.

    Dentro un'app PyInstaller i percorsi dei certificati di sistema non
    esistono: senza questo, il download HTTPS dei pesi fallirebbe con
    CERTIFICATE_VERIFY_FAILED.
    """
    try:
        import certifi
    except ImportError:  # ambiente di sviluppo senza certifi: ok così
        return
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())


def prepare_runtime_env() -> None:
    """Da chiamare ai punti d'ingresso (worker, CLI) PRIMA di importare torch.

    PYTORCH_ENABLE_MPS_FALLBACK: un'operazione non implementata su MPS
    ripiega su CPU invece di abortire il job; il controllo di validità
    resta comunque a valle (validate_mps).
    """
    ensure_ca_bundle()
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def _cuda_available() -> bool:
    import torch

    return bool(torch.cuda.is_available())


def _mps_available() -> bool:
    import torch

    backend = getattr(torch.backends, "mps", None)
    return bool(backend is not None and backend.is_available())


def verdict_path() -> Path:
    return paths.calibration_path().parent / "device.json"


def load_mps_verdict() -> bool | None:
    """True/False se MPS è già stato verificato su questa macchina, None se mai."""
    path = verdict_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("mps_ok")
    return value if isinstance(value, bool) else None


def save_mps_verdict(ok: bool, detail: str) -> None:
    path = verdict_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mps_ok": ok, "detail": detail}, indent=2), encoding="utf-8")


def resolve_device(
    requested: str,
    cuda_available: Callable[[], bool] = _cuda_available,
    mps_available: Callable[[], bool] = _mps_available,
    mps_verdict: Callable[[], bool | None] = load_mps_verdict,
) -> str:
    """Da "auto"/"cpu"/"cuda"/"mps" al device effettivo.

    Le sonde sono iniettabili per testare senza torch.
    """
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not cuda_available():
            raise RuntimeError("CUDA richiesto ma non disponibile: usa --device cpu o auto")
        return "cuda"
    if requested == "mps":
        if not mps_available():
            raise RuntimeError("MPS richiesto ma non disponibile: usa --device cpu o auto")
        return "mps"
    if requested == "auto":
        if cuda_available():
            return "cuda"
        if mps_available() and mps_verdict() is True:
            return "mps"
        return "cpu"
    raise ValueError(f"device sconosciuto: {requested!r}")


def mps_needs_validation() -> bool:
    """MPS c'è ma non è mai stato verificato su questa macchina."""
    return load_mps_verdict() is None and _mps_available()
