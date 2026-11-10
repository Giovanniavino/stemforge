"""Cosa l'installer lascia nel sistema, letto dal sistema stesso (§9.7).

Lo usa packaging/ci/verify_windows_installer.py. Le cartelle si chiedono
a Windows (SHGetKnownFolderPath) e non si ricostruiscono da %USERPROFILE%:
Desktop e Documenti reindirizzati da OneDrive sono la norma, non
l'eccezione, e un controllo sul percorso sbagliato passerebbe sempre.
"""

from __future__ import annotations

import ctypes
import math
import os
import struct
import subprocess
import tempfile
import time
import uuid
import wave
import winreg
from pathlib import Path

APP_EXE = "StemForge.exe"
APP_ID = "{6B7C2E1F-4A3D-4F8B-9C21-5E0D7A9B3F42}"
PROG_ID = "StemForge.AudioFile"
EXTENSIONS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif")
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
CLASSES = r"Software\Classes"
FOLDERID_PROGRAMS = "A77F5D77-2E2B-44C3-A6A2-ABA601054A51"
FOLDERID_DESKTOP = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
FOLDERID_MUSIC = "4BD8D571-6D19-48D3-BE97-422220080E43"
_SHORTCUT = "StemForge.lnk"
_TONE_RATE = 44100
_TONE_SECONDS = 2


class _Guid(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]


def known_folder(folder_id: str) -> Path:
    guid = _Guid.from_buffer_copy(uuid.UUID(folder_id).bytes_le)
    out = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
    if result != 0:
        raise OSError(f"SHGetKnownFolderPath({folder_id}) = {result:#x}")
    try:
        return Path(out.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def _value(root: int, key: str, name: str = "") -> str | None:
    try:
        with winreg.OpenKey(root, key) as handle:
            return str(winreg.QueryValueEx(handle, name)[0])
    except FileNotFoundError:
        return None


def _key_exists(key: str) -> bool:
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, key).Close()
        return True
    except FileNotFoundError:
        return False


def installed_dir() -> Path | None:
    location = _value(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "InstallLocation")
    return Path(location) if location else None


def uninstall_command() -> list[str]:
    command = _value(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "UninstallString")
    if not command:
        raise AssertionError("voce di disinstallazione assente dal registro")
    return [command.strip('"')]


def default_associations() -> dict[str, dict[str, str | None]]:
    """Chi apre ogni estensione col doppio click: non deve cambiare mai."""
    explorer = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
    return {
        ext: {
            "hkcu": _value(winreg.HKEY_CURRENT_USER, rf"{CLASSES}\{ext}"),
            "hkcr": _value(winreg.HKEY_CLASSES_ROOT, ext),
            "user_choice": _value(winreg.HKEY_CURRENT_USER, rf"{explorer}\{ext}\UserChoice", "ProgId"),
        }
        for ext in EXTENSIONS
    }


def _shortcut_target(link: Path) -> Path:
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "(New-Object -ComObject WScript.Shell).CreateShortcut($env:SF_LINK).TargetPath"
    )
    env = {**os.environ, "SF_LINK": str(link)}
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env,
                         capture_output=True, check=True).stdout.decode("utf-8-sig")
    return Path(out.strip())


def check_start_menu(exe: Path) -> str:
    link = known_folder(FOLDERID_PROGRAMS) / _SHORTCUT
    if not link.is_file():
        raise AssertionError(f"collegamento nel menu Start assente: {link}")
    target = _shortcut_target(link)
    if os.path.normcase(target) != os.path.normcase(exe):
        raise AssertionError(f"il collegamento punta a {target} invece di {exe}")
    return f"menu Start: {link} -> {target}"


def check_no_desktop_icon() -> str:
    link = known_folder(FOLDERID_DESKTOP) / _SHORTCUT
    if link.exists():
        raise AssertionError(f"icona sul desktop creata senza averla chiesta: {link}")
    return f"nessuna icona sul desktop (opzione non scelta): {link.parent}"


def check_open_with(exe: Path) -> str:
    expected = f'"{exe}" "%1"'
    hkcu = winreg.HKEY_CURRENT_USER
    for key in (rf"{CLASSES}\{PROG_ID}\shell\open\command", rf"{CLASSES}\Applications\{APP_EXE}\shell\open\command"):
        if _value(hkcu, key) != expected:
            raise AssertionError(f"{key} = {_value(hkcu, key)!r} invece di {expected!r}")
    for ext in EXTENSIONS:
        if _value(hkcu, rf"{CLASSES}\Applications\{APP_EXE}\SupportedTypes", ext) is None:
            raise AssertionError(f"{ext} assente da SupportedTypes")
        if _value(hkcu, rf"{CLASSES}\{ext}\OpenWithProgids", PROG_ID) is None:
            raise AssertionError(f"{PROG_ID} assente da {ext}\\OpenWithProgids")
    return f"'Apri con' registrato per {len(EXTENSIONS)} estensioni, comando {expected}"


def check_integration_removed() -> str:
    leftovers = [k for k in (rf"{CLASSES}\{PROG_ID}", rf"{CLASSES}\Applications\{APP_EXE}", UNINSTALL_KEY)
                 if _key_exists(k)]
    leftovers += [f"{ext}\\OpenWithProgids\\{PROG_ID}" for ext in EXTENSIONS
                  if _value(winreg.HKEY_CURRENT_USER, rf"{CLASSES}\{ext}\OpenWithProgids", PROG_ID) is not None]
    if (known_folder(FOLDERID_PROGRAMS) / _SHORTCUT).exists():
        leftovers.append("collegamento nel menu Start")
    if leftovers:
        raise AssertionError(f"rimasto dopo la disinstallazione: {leftovers}")
    return "registro e menu Start ripuliti"


def data_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "StemForge"


def models_footprint() -> tuple[int, int] | None:
    """(numero di file, byte) dei modelli scaricati: la disinstallazione
    silenziosa non deve toccarli."""
    models = data_dir() / "models"
    if not models.is_dir():
        return None
    files = [p for p in models.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def tree_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def longest_path(root: Path) -> int:
    return max(len(str(p)) for p in root.rglob("*"))


def _write_tone(path: Path) -> None:
    """Un wav stereo a 16 bit generato qui: nessun materiale protetto."""
    frames = bytearray()
    for i in range(_TONE_RATE * _TONE_SECONDS):
        sample = int(12000 * math.sin(2 * math.pi * 330.0 * i / _TONE_RATE))
        frames += struct.pack("<hh", sample, sample)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(_TONE_RATE)
        handle.writeframes(bytes(frames))


def check_open_with_launch(app_dir: Path, alive_s: float) -> str:
    """Lancia l'app esattamente come "Apri con": il comando del ProgID con %1."""
    command = _value(winreg.HKEY_CURRENT_USER, rf"{CLASSES}\{PROG_ID}\shell\open\command")
    if not command or str(app_dir) not in command:
        raise AssertionError(f"comando 'Apri con' inatteso: {command!r}")
    log = data_dir() / "logs" / "stemforge.log"
    offset = log.stat().st_size if log.exists() else 0
    with tempfile.TemporaryDirectory(prefix="stemforge-openwith-") as tmp:
        song = Path(tmp) / "brano di prova àè.wav"
        _write_tone(song)
        proc = subprocess.Popen(command.replace("%1", str(song)))
        try:
            time.sleep(alive_s)
            if proc.poll() is not None:
                raise AssertionError(f"l'app aperta con un wav è uscita da sola (codice {proc.returncode})")
        finally:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
            proc.wait(timeout=30)
    if not log.exists():
        raise AssertionError(f"log non scritto: {log}")
    with log.open("rb") as handle:
        handle.seek(offset)
        appended = handle.read().decode("utf-8", errors="replace")
    if "Traceback" in appended:
        raise AssertionError(f"traceback nel log dopo 'Apri con':\n{appended[-4000:]}")
    return f"'Apri con' su un wav: app viva dopo {alive_s:.0f} s, log senza traceback ({len(appended)} caratteri nuovi)"
