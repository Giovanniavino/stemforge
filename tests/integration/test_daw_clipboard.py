"""Formati nativi di Windows prodotti davvero da Qt per il MIME del drag.

Il QMimeData di build_mime_data va negli appunti di Windows (stesso
convertitore QWindowsMimeURI del drag OLE) e lo si rilegge con user32 come
farebbe una DAW: EnumClipboardFormats per l'elenco, DragQueryFileW sul
CF_HDROP per i percorsi. Gira in un processo figlio perché serve il plugin
QPA "windows": gli altri test della UI usano "offscreen", i cui appunti
sono finti.

Gli appunti differiscono dal drag in un punto, letto nel sorgente di Qt
(qwindowsdropdataobject.cpp): nel drag, con solo `text/uri-list` e file
locali, Qt rifiuta GetData per CF_TEXT, CF_UNICODETEXT e
UniformResourceLocator(W); negli appunti (QWindowsOleDataObject) quel
filtro non c'è e gli URL compaiono. Qui si verifica quindi CF_HDROP e il
suo contenuto, più la precondizione del filtro (un solo formato MIME).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

CF_TEXT = 1
CF_UNICODETEXT = 13
CF_HDROP = 15
_OPEN_ATTEMPTS = 20
_OPEN_RETRY_S = 0.05
_CHILD_TIMEOUT_S = 60
_NAME_BUFFER = 256
_LONG_SEGMENT = "cartella con un nome lungo per superare MAX_PATH àèìòù"


def _user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT
    user32.GetClipboardFormatNameW.argtypes = [wintypes.UINT, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                       wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    return ctypes, user32, shell32


def _open_clipboard(user32) -> None:
    # gli appunti sono di tutto il desktop: un altro processo può tenerli
    for _ in range(_OPEN_ATTEMPTS):
        if user32.OpenClipboard(None):
            return
        time.sleep(_OPEN_RETRY_S)
    raise RuntimeError("OpenClipboard non riuscita: appunti occupati")


def _format_names(ctypes, user32) -> dict[str, str]:
    names: dict[str, str] = {}
    fmt = user32.EnumClipboardFormats(0)
    while fmt:
        buffer = ctypes.create_unicode_buffer(_NAME_BUFFER)
        length = user32.GetClipboardFormatNameW(fmt, buffer, _NAME_BUFFER)
        names[str(fmt)] = buffer.value if length else ""
        fmt = user32.EnumClipboardFormats(fmt)
    return names


def _hdrop_files(ctypes, user32, shell32) -> list[str]:
    handle = user32.GetClipboardData(CF_HDROP)
    if not handle:
        return []
    count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
    files = []
    for index in range(count):
        size = shell32.DragQueryFileW(handle, index, None, 0) + 1
        buffer = ctypes.create_unicode_buffer(size)
        shell32.DragQueryFileW(handle, index, buffer, size)
        files.append(buffer.value)
    return files


def probe(paths: list[str]) -> dict:
    """Nel figlio: MIME negli appunti, poi lettura nativa come una DAW."""
    from PySide6.QtGui import QGuiApplication

    from stemforge.ui.drag_export import build_mime_data

    app = QGuiApplication(["probe", "-platform", "windows"])
    mime = build_mime_data([Path(p) for p in paths])
    report = {"platform": app.platformName(), "mime_formats": mime.formats(),
              "mime_urls": [url.toString() for url in mime.urls()]}
    clipboard = app.clipboard()
    clipboard.setMimeData(mime)
    app.processEvents()
    ctypes, user32, shell32 = _user32()
    _open_clipboard(user32)
    try:
        report["formats"] = _format_names(ctypes, user32)
        report["hdrop"] = _hdrop_files(ctypes, user32, shell32)
    finally:
        user32.CloseClipboard()
    # non lasciare i nostri file negli appunti dell'utente
    clipboard.clear()
    app.processEvents()
    return report


def _make_files(root: Path) -> list[str]:
    plain = root / "Brano con spazi è ü 日本" / "vocals.wav"
    odd = root / "Brano #1 [mix] 100%" / "drums.wav"
    deep = root.joinpath(*([_LONG_SEGMENT] * 5), "bass.wav")
    created = []
    for path in (plain, odd, deep):
        verbatim = "\\\\?\\" + str(path)
        os.makedirs(os.path.dirname(verbatim), exist_ok=True)
        with open(verbatim, "wb") as handle:
            handle.write(b"RIFF")
        created.append(str(path))
    return created


def _run_probe(files: list[str]) -> dict:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "windows"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[2] / "src"), env.get("PYTHONPATH", "")])
    done = subprocess.run(
        [sys.executable, __file__, *files], capture_output=True, text=True,
        encoding="utf-8", env=env, timeout=_CHILD_TIMEOUT_S, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(sys.platform != "win32", reason="formati di appunti nativi di Windows")
def test_qt_puts_cf_hdrop_with_exact_paths_on_windows(tmp_path: Path):
    files = _make_files(tmp_path)
    report = _run_probe(files)

    assert report["platform"] == "windows"
    # precondizione del filtro di qwindowsdropdataobject.cpp: un solo formato
    assert report["mime_formats"] == ["text/uri-list"]
    assert str(CF_HDROP) in report["formats"], report["formats"]
    hdrop = report["hdrop"]
    assert len(hdrop) == len(files)
    for got, original in zip(hdrop, files):
        assert not got.startswith("\\\\?\\"), got
        assert "/" not in got, got
        # oltre MAX_PATH le cartelle passano ai nomi 8.3; se il volume li
        # ha disattivati il percorso resta quello lungo (con un warning)
        assert len(got) < 260 or got == original, got
        assert Path(got).name == Path(original).name
        assert os.path.samefile("\\\\?\\" + got, "\\\\?\\" + original)
    # i primi due sono corti: arrivano identici, unicode e spazi compresi
    assert hdrop[:2] == files[:2]
    assert len(files[2]) >= 260, "il terzo file deve davvero superare MAX_PATH"


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1:]), ensure_ascii=True))
