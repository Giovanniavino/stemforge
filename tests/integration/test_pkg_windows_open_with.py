"""Il collaudo di "Apri con" distingue l'app avviata da un avvio fallito (§9.7).

Un exe PyInstaller che fallisce all'avvio resta vivo con una MessageBox
d'errore: "processo vivo dopo 10 s" passerebbe lo stesso.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="finestre Win32: solo Windows")

ROOT = Path(__file__).resolve().parents[2]
_WAIT_S = 20
# come il bootloader di PyInstaller quando lo script muore all'avvio
_ERROR_BOX = "import ctypes; ctypes.windll.user32.MessageBoxW(None, 'Unhandled exception', 'StemForge', 0x10)"


@pytest.fixture()
def wi(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ROOT / "packaging" / "windows"))
    import windows_integration

    return windows_integration


def test_error_dialog_is_not_the_main_window(wi):
    # il python.exe di un venv è un lanciatore: la finestra sarebbe del processo figlio
    proc = subprocess.Popen([sys._base_executable, "-I", "-c", _ERROR_BOX])
    try:
        deadline = time.monotonic() + _WAIT_S
        while not wi.process_windows(proc.pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert ("#32770", "StemForge") in wi.process_windows(proc.pid)
        with pytest.raises(AssertionError, match="nessuna finestra principale"):
            wi._check_main_window(proc.pid)
    finally:
        proc.kill()
        proc.wait(timeout=30)
