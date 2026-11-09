"""Come si lancia il processo figlio (BUILD_SPEC D2).

Senza Qt: lo usano sia il bridge dell'UI sia il collaudo (selftest), che
così esercita ESATTAMENTE il percorso di lancio dell'app vera.
"""

from __future__ import annotations

import sys


def worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        # nel bundle PyInstaller l'app rilancia sé stessa in modalità worker
        return [sys.executable, "--worker"]
    return [sys.executable, "-m", "stemforge.worker.runner"]
