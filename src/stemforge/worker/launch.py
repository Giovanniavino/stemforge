"""Come si lanciano i processi figli (BUILD_SPEC D2, §10.5, §9.9).

Senza Qt: lo usano sia il bridge dell'UI sia il collaudo (selftest), che
così esercita ESATTAMENTE il percorso di lancio dell'app vera, e la
diagnostica, che fa girare il collaudo in un processo a parte per non
caricare torch nel processo dell'interfaccia.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def worker_command() -> list[str]:
    if _frozen():
        # nel bundle PyInstaller l'app rilancia sé stessa in modalità worker
        return [sys.executable, "--worker"]
    return [sys.executable, "-m", "stemforge.worker.runner"]


def selftest_command(report: Path, offline: bool = True) -> list[str]:
    """`StemForge --selftest --report FILE [--offline]` (§10.5).

    Nel pacchetto è lo stesso eseguibile dell'app (che aggiunge il
    controllo dell'interfaccia); dai sorgenti è il modulo del collaudo.
    """
    flags = ["--selftest", "--report", str(report)] + (["--offline"] if offline else [])
    if _frozen():
        return [sys.executable, *flags]
    return [sys.executable, "-m", "stemforge.worker.selftest", *flags]
