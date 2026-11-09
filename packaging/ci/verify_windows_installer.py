"""Collaudo dell'installer Windows così come lo riceve l'utente.

    python packaging/ci/verify_windows_installer.py <setup.exe> <report.json>

Installa in silenzio (per utente, senza amministratore), controlla
collegamento nel menu Start e "Apri con", collauda l'app INSTALLATA,
poi la disinstalla e verifica che sia sparita davvero.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HERE = Path(__file__).resolve().parent
_INSTALL_TIMEOUT_S = 15 * 60


def _install(setup: Path, target: Path) -> None:
    log = target.parent / "install.log"
    subprocess.run(
        [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
         f"/DIR={target}", f"/LOG={log}"],
        check=True, timeout=_INSTALL_TIMEOUT_S,
    )
    if not (target / "StemForge.exe").is_file():
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "nessun log")
        raise AssertionError("StemForge.exe non installato")


def _check_integration() -> None:
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    if not (start_menu / "StemForge.lnk").is_file():
        raise AssertionError(f"collegamento nel menu Start assente in {start_menu}")
    key = r"Software\Classes\Applications\StemForge.exe\SupportedTypes"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
        winreg.QueryValueEx(handle, ".m4a")  # "Apri con" registrato
    print("menu Start e 'Apri con': ok")


def _uninstall(target: Path) -> None:
    subprocess.run([str(target / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    # il disinstallatore si copia in una cartella temporanea e ritorna subito
    for _ in range(120):
        if not (target / "StemForge.exe").exists():
            print("disinstallazione: ok")
            return
        time.sleep(1)
    raise AssertionError("StemForge.exe ancora presente dopo la disinstallazione")


def main() -> int:
    setup, report = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    target = Path(tempfile.mkdtemp(prefix="stemforge-install-")) / "StemForge"
    _install(setup, target)
    _check_integration()
    code = subprocess.run(
        [sys.executable, str(HERE / "run_selftest.py"), str(target / "StemForge.exe"), str(report)]
    ).returncode
    _uninstall(target)
    return code


if __name__ == "__main__":
    sys.exit(main())
