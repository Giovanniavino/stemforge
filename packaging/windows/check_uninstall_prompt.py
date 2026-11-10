"""Collaudo della domanda di disinstallazione (§9.7), con risposte vere.

    python packaging/windows/check_uninstall_prompt.py <report.json> [--iscc ISCC.exe]

Compila stemforge.iss con un'app finta e /DDataDirName=<cartella finta>,
così un "Sì" non può mai cancellare i modelli veri di questa macchina.
Poi tre giri, ognuno installa in silenzio e disinstalla:

- silenzioso: nessuna domanda, la cartella dati resta;
- interattivo, risposta No: la domanda compare una volta, il pulsante
  predefinito è No, la cartella resta;
- interattivo, risposta Sì: la cartella sparisce.

Un quarto giro, con un installer compilato come se i percorsi lunghi di
Windows fossero spenti (/DAssumeLongPathsDisabled), controlla che una
/DIR= di un carattere oltre il limite sia rifiutata e una al limite no.

Le finestre del disinstallatore (MessageBox Win32, classe #32770) si
leggono e si premono con user32: niente dipendenze, niente click a
coordinate.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import windows_integration as wi  # noqa: E402
from build_installer import compile_installer  # noqa: E402

FAKE_DATA_DIR = "StemForge-collaudo-disinstallazione"
# un file profondo come quelli di torch e Qt: fissa il limite della cartella
FAKE_DEEP_FILE = "_internal/" + "/".join(["cartella-profonda-di-prova"] * 4) + "/libreria.dll"
_IDOK, _IDCANCEL, _IDYES, _IDNO = 1, 2, 6, 7
_BM_CLICK = 0x00F5
_DM_GETDEFID = 0x0400
_DC_HASDEFID = 0x534B
_MSGBOX_TEXT_ID = 0xFFFF  # il testo di una MessageBox sta nello Static con questo id
_COMPILE_TIMEOUT_S = 300
_DIALOG_TIMEOUT_S = 120
_POLL_S = 0.2

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumWindows.argtypes = [_EnumProc, wt.LPARAM]
_user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
_user32.GetDlgItem.restype = wt.HWND
_user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.SendMessageW.restype = ctypes.c_ssize_t
_user32.GetDlgItemTextW.argtypes = [wt.HWND, ctypes.c_int, wt.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_kernel32.OpenProcess.restype = wt.HANDLE
_kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
_kernel32.CloseHandle.argtypes = [wt.HANDLE]
_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x102


def _message_boxes() -> list[tuple[int, str]]:
    """(handle, testo) delle MessageBox visibili che parlano di StemForge."""
    found: list[tuple[int, str]] = []

    def visit(hwnd: int, _: int) -> bool:
        name = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, name, len(name))
        if name.value == "#32770" and _user32.IsWindowVisible(hwnd):
            text = ctypes.create_unicode_buffer(4096)
            _user32.GetDlgItemTextW(hwnd, _MSGBOX_TEXT_ID, text, len(text))
            if "StemForge" in text.value:
                found.append((hwnd, text.value))
        return True

    _user32.EnumWindows(_EnumProc(visit), 0)
    return found


def _default_button(hwnd: int) -> int | None:
    result = _user32.SendMessageW(hwnd, _DM_GETDEFID, 0, 0)
    return result & 0xFFFF if (result >> 16) & 0xFFFF == _DC_HASDEFID else None


def _press(hwnd: int, button_id: int) -> bool:
    button = _user32.GetDlgItem(hwnd, button_id)
    if not button:
        return False
    _user32.SendMessageW(button, _BM_CLICK, 0, 0)
    return True


def _answer(hwnd: int, text: str, data_dir: Path, answer: int) -> dict:
    """Risponde a una finestra: Sì alla conferma, `answer` alla nostra domanda, OK al resto."""
    if str(data_dir) in text:
        seen = {"kind": "domanda-dati", "default": _default_button(hwnd), "pressed": answer}
    elif _user32.GetDlgItem(hwnd, _IDYES):
        seen = {"kind": "conferma", "pressed": _IDYES}
    else:
        # in una MessageBox col solo OK il pulsante ha l'id di IDCANCEL (Esc la chiude)
        ok_button = _IDOK if _user32.GetDlgItem(hwnd, _IDOK) else _IDCANCEL
        seen = {"kind": "avviso", "pressed": ok_button}
    seen["text"] = text
    if not _press(hwnd, seen["pressed"]):
        raise AssertionError(f"pulsante {seen['pressed']} assente in: {text!r}")
    return seen


def _process_alive(pid: int) -> bool:
    handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return _kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(handle)


def _drive_dialogs(data_dir: Path, answer: int, command: list[str]) -> list[dict]:
    """Avvia il disinstallatore interattivo e risponde finché non ha finito.

    Il disinstallatore si copia in %TEMP% e la copia possiede le finestre;
    il processo lanciato aspetta che la conferma iniziale abbia risposta,
    quindi non lo si attende prima di rispondere (sarebbe una gara)."""
    launcher = subprocess.Popen(command)
    dialogs: list[dict] = []
    handled: set[int] = set()
    owners: set[int] = set()
    deadline = time.monotonic() + _DIALOG_TIMEOUT_S
    while time.monotonic() < deadline:
        for hwnd, text in [(h, t) for h, t in _message_boxes() if h not in handled]:
            handled.add(hwnd)
            owners.add(_window_pid(hwnd))
            dialogs.append(_answer(hwnd, text, data_dir, answer))
        if owners and launcher.poll() is not None and not any(_process_alive(pid) for pid in owners):
            if launcher.returncode != 0:
                raise AssertionError(f"disinstallatore uscito con {launcher.returncode}; finestre: {dialogs}")
            return dialogs
        time.sleep(_POLL_S)
    launcher.kill()
    raise AssertionError(f"disinstallazione interattiva non conclusa; finestre viste: {dialogs}")


def _window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _build_installer(iscc: Path, work: Path, defines: dict[str, str]) -> Path:
    packaging = work / "packaging"
    (packaging / "windows").mkdir(parents=True)
    shutil.copy(HERE / "stemforge.iss", packaging / "windows")
    app = packaging / "dist" / "StemForge"
    (app / FAKE_DEEP_FILE).parent.mkdir(parents=True)
    (app / wi.APP_EXE).write_bytes(b"MZ app finta: il collaudo riguarda l'installer")
    (app / FAKE_DEEP_FILE).write_text("dato", encoding="utf-8")
    return compile_installer(iscc, packaging, "0.0.0", {"DataDirName": FAKE_DATA_DIR, **defines})


def _install(setup: Path, target: Path) -> None:
    subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
                    f"/DIR={target}"], check=True, timeout=_COMPILE_TIMEOUT_S)
    if wi.installed_dir() is None:
        raise AssertionError("installazione di prova non registrata")


def _fill_fake_data(data_dir: Path) -> None:
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    (data_dir / "models" / "finto.th").write_bytes(b"peso finto")
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "logs" / "stemforge.log").write_text("log finto\n", encoding="utf-8")


def _silent_round(setup: Path, target: Path, data_dir: Path) -> dict:
    _install(setup, target)
    _fill_fake_data(data_dir)
    command = wi.uninstall_command()
    subprocess.run([*command, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    _drive_dialogs_absent(command)
    if not (data_dir / "models" / "finto.th").is_file():
        raise AssertionError("la disinstallazione silenziosa ha cancellato i dati dell'utente")
    return {"round": "silenzioso", "dialogs": [], "data_kept": True}


def _drive_dialogs_absent(command: list[str]) -> None:
    deadline = time.monotonic() + _DIALOG_TIMEOUT_S
    while time.monotonic() < deadline:
        if _message_boxes():
            raise AssertionError(f"finestre in modalità silenziosa: {_message_boxes()}")
        if wi.installed_dir() is None and not Path(command[0]).exists():
            return
        time.sleep(_POLL_S)
    raise AssertionError("disinstallazione silenziosa non conclusa")


def _interactive_round(setup: Path, target: Path, data_dir: Path, answer: int) -> dict:
    _install(setup, target)
    _fill_fake_data(data_dir)
    dialogs = _drive_dialogs(data_dir, answer, wi.uninstall_command())
    questions = [d for d in dialogs if d["kind"] == "domanda-dati"]
    if len(questions) != 1:
        raise AssertionError(f"attesa una domanda sui dati, viste {len(questions)}: {dialogs}")
    if questions[0]["default"] != _IDNO:
        raise AssertionError(f"pulsante predefinito {questions[0]['default']} invece di No")
    if any(d["kind"] == "avviso" and str(data_dir) in d["text"] for d in dialogs):
        raise AssertionError(f"eliminazione fallita: {dialogs}")
    kept = data_dir.exists()
    if kept != (answer == _IDNO):
        raise AssertionError(f"risposta {'No' if answer == _IDNO else 'Sì'} ma cartella dati presente={kept}")
    name = "interattivo-no" if answer == _IDNO else "interattivo-si"
    return {"round": name, "dialogs": dialogs, "data_kept": kept}


def _dir_of_length(base: Path, length: int) -> Path:
    """Una cartella sotto `base` lunga esattamente `length` caratteri."""
    padding = length - len(str(base / "StemForge")) - 1
    if padding < 1:
        raise ValueError(f"{base} è già più lunga di {length} caratteri")
    return base / ("p" * padding) / "StemForge"


def _long_path_round(iscc: Path, work: Path) -> dict:
    """Con i percorsi lunghi di Windows spenti (simulati: il dev-box li ha
    accesi) una cartella troppo lunga è rifiutata, quella al limite no."""
    setup = _build_installer(iscc, work / "bl", {"AssumeLongPathsDisabled": "1"})
    limit = 259 - 1 - len(FAKE_DEEP_FILE)
    too_long = _dir_of_length(work, limit + 1)
    code = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
                           f"/DIR={too_long}"], timeout=_COMPILE_TIMEOUT_S).returncode
    if code == 0 or wi.installed_dir() is not None or (too_long / wi.APP_EXE).exists():
        raise AssertionError(f"cartella di {limit + 1} caratteri accettata (uscita {code})")
    at_limit = _dir_of_length(work, limit)
    _install(setup, at_limit)
    if not (at_limit / FAKE_DEEP_FILE).is_file():
        raise AssertionError("file profondo non installato nella cartella al limite")
    command = wi.uninstall_command()
    subprocess.run([*command, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    _drive_dialogs_absent(command)
    return {"round": "percorso-lungo", "dialogs": [], "limit_chars": limit, "refused_exit_code": code,
            "data_kept": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--iscc", type=Path, default=wi.find_iscc())
    args = parser.parse_args()
    if args.iscc is None:
        print("Inno Setup 6 (ISCC.exe) non trovato: passa --iscc", file=sys.stderr)
        return 2
    if wi.installed_dir() is not None:
        print(f"StemForge è già installato in {wi.installed_dir()}: non lo tocco", file=sys.stderr)
        return 2
    data_dir = Path(os.environ["LOCALAPPDATA"]) / FAKE_DATA_DIR
    rounds = []
    with tempfile.TemporaryDirectory(prefix="stemforge-prompt-") as tmp:
        setup = _build_installer(args.iscc, Path(tmp) / "build", {})
        target = Path(tmp) / "Programmi di prova àè" / "StemForge"
        try:
            rounds.append(_silent_round(setup, target, data_dir))
            rounds.append(_interactive_round(setup, target, data_dir, _IDNO))
            rounds.append(_interactive_round(setup, target, data_dir, _IDYES))
            rounds.append(_long_path_round(args.iscc, Path(tmp)))
        finally:
            if wi.installed_dir() is not None:  # un giro fallito non lascia l'installazione di prova
                command = wi.uninstall_command()
                subprocess.run([*command, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=False)
                _drive_dialogs_absent(command)
            shutil.rmtree(data_dir, ignore_errors=True)
    args.report.write_text(json.dumps(rounds, indent=2, ensure_ascii=False), encoding="utf-8")
    for result in rounds:
        print(f"ok: {result['round']}: {len(result['dialogs'])} finestre, dati rimasti={result['data_kept']}")
    print("DOMANDA DI DISINSTALLAZIONE COLLAUDATA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
