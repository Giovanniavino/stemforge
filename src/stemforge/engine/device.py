"""Ambiente di esecuzione: device di calcolo, verdetti, certificati, RAM.

BUILD_SPEC §4.2, §5.6, §6.1, D6, D8. Tre famiglie di macchine:

- Mac Intel e PC senza GPU NVIDIA: CPU.
- PC con GPU NVIDIA (build CUDA): CUDA.
- Mac Apple Silicon: MPS, la GPU integrata.

Un acceleratore non si accende sulla fiducia (D8): al primo uso un
controllo confronta la sua uscita con quella della CPU sullo stesso
audio (calibrate.validate_accelerator) e il verdetto si salva per
macchina in device.json, uno per acceleratore. Senza verdetto positivo
"auto" resta su CPU: la qualità viene prima del tempo (§0). Forzare un
acceleratore resta una scelta dell'utente.

Questo modulo è una delle sedi ammesse per le API di piattaforma
(§10.4): qui si legge la RAM disponibile, con ctypes su Windows e
macOS e /proc/meminfo su Linux, senza dipendenze nuove. torch è
importato in modo pigro perché i test unitari girano senza.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable

from stemforge.engine import paths
from stemforge.engine.errors import DeviceUnavailableError

log = logging.getLogger(__name__)

# In ordine di preferenza per "auto": su una macchina ce n'è al più uno.
ACCELERATORS = ("cuda", "mps")

Probe = Callable[[], bool]
Verdict = Callable[[str], "bool | None"]


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
    resta comunque a valle (D8).
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


# -- verdetti (D8) -----------------------------------------------------------


def verdict_path() -> Path:
    return paths.calibration_path().parent / "device.json"


def _read_verdicts() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(verdict_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    verdicts = {k: v for k, v in data.items() if k in ACCELERATORS and isinstance(v, dict)}
    # formato della v2.3: {"mps_ok": bool, "detail": str}
    if "mps" not in verdicts and isinstance(data.get("mps_ok"), bool):
        verdicts["mps"] = {"ok": data["mps_ok"], "detail": str(data.get("detail", ""))}
    return verdicts


def load_verdict(accelerator: str) -> bool | None:
    """True/False se l'acceleratore è già stato verificato qui, None se mai."""
    value = _read_verdicts().get(accelerator, {}).get("ok")
    return value if isinstance(value, bool) else None


def save_verdict(accelerator: str, ok: bool, detail: str) -> None:
    if accelerator not in ACCELERATORS:
        raise ValueError(f"acceleratore sconosciuto: {accelerator!r}")
    verdicts = _read_verdicts()
    verdicts[accelerator] = {"ok": ok, "detail": detail}
    path = verdict_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(verdicts, indent=2), encoding="utf-8")


def _probes(cuda_available: Probe, mps_available: Probe) -> dict[str, Probe]:
    return {"cuda": cuda_available, "mps": mps_available}


def resolve_device(
    requested: str,
    cuda_available: Probe = _cuda_available,
    mps_available: Probe = _mps_available,
    verdict: Verdict = load_verdict,
) -> str:
    """Da "auto"/"cpu"/"cuda"/"mps" al device effettivo (D8).

    Le sonde sono iniettabili per testare senza torch.
    """
    probes = _probes(cuda_available, mps_available)
    if requested == "cpu":
        return "cpu"
    if requested in probes:
        if not probes[requested]():
            raise DeviceUnavailableError(
                "err.device_unavailable", f"{requested} richiesto ma assente",
                device=requested.upper(),
            )
        return requested
    if requested == "auto":
        for accelerator in ACCELERATORS:
            if probes[accelerator]() and verdict(accelerator) is True:
                return accelerator
        return "cpu"
    raise ValueError(f"device sconosciuto: {requested!r}")


def unverified_accelerators(
    cuda_available: Probe = _cuda_available,
    mps_available: Probe = _mps_available,
    verdict: Verdict = load_verdict,
) -> tuple[str, ...]:
    """Acceleratori presenti ma mai confrontati con la CPU su questa macchina."""
    probes = _probes(cuda_available, mps_available)
    return tuple(a for a in ACCELERATORS if verdict(a) is None and probes[a]())


# -- RAM disponibile (§6.1 punto 3) ------------------------------------------


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _windows_available() -> int | None:
    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return None
    return int(status.ullAvailPhys)


def _sysctl_int(libc: ctypes.CDLL, name: str) -> int | None:
    # 8 byte azzerati: i contatori di pagine sono a 32 bit, hw.memsize a
    # 64; entrambe le architetture dei Mac sono little-endian
    value = ctypes.c_uint64(0)
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if libc.sysctlbyname(name.encode(), ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
        return None
    return int(value.value)


# Pagine che macOS restituisce senza swappare: libere, speculative,
# eliminabili e la cache dei file (è ciò che Monitoraggio Attività
# conta come disponibile, oltre a "memoria app" e "wired").
_MAC_RECLAIMABLE = (
    "vm.page_free_count",
    "vm.page_speculative_count",
    "vm.page_purgeable_count",
    "vm.page_pageable_external_count",
)


def _macos_available() -> int | None:
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    page = _sysctl_int(libc, "hw.pagesize")
    counts = [_sysctl_int(libc, name) for name in _MAC_RECLAIMABLE]
    if page and all(c is not None for c in counts):
        return page * sum(c for c in counts if c is not None)
    total = _sysctl_int(libc, "hw.memsize")
    # senza contatori di pagine: metà della RAM fisica, prudente
    return total // 2 if total else None


def parse_meminfo(text: str) -> int | None:
    """MemAvailable di /proc/meminfo, in byte (il kernel lo stima per noi)."""
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1]) * 1024
    return None


def _linux_available() -> int | None:
    return parse_meminfo(Path("/proc/meminfo").read_text(encoding="ascii", errors="replace"))


def available_memory_bytes(platform: str | None = None) -> int | None:
    """RAM che il job può usare senza far swappare la macchina; None se ignota.

    Un errore di lettura non è un guasto del job: senza il numero si
    usano i blocchi di sempre (audio_io.BLOCK_LENGTH_S).
    """
    platform = sys.platform if platform is None else platform
    reader = {"win32": _windows_available, "darwin": _macos_available}.get(
        platform, _linux_available
    )
    try:
        value = reader()
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        log.warning("RAM disponibile non leggibile su %s: %r", platform, exc)
        return None
    return value if value is not None and value > 0 else None
