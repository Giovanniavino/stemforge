"""Contenuto del drag verso le DAW (§7.2, §7.2.1).

Un solo formato, `text/uri-list`, su ogni sistema. È una scelta, non una
pigrizia (fonti in docs/daw/README.md):

- **Windows**: Qt traduce gli URL locali in `CF_HDROP` (DROPFILES wide),
  il formato che leggono Explorer, JUCE e quindi tutte le DAW. Se il
  QMimeData ha *solo* `text/uri-list`, il drag di Qt rifiuta i formati
  testo e `UniformResourceLocator(W)` (qwindowsdropdataobject.cpp): la DAW
  vede un drop di file, non un link. Un formato in più toglierebbe quel
  filtro, quindi non se ne aggiunge nessuno.
- **macOS**: con più URL Qt crea un NSDraggingItem per file
  (`public.file-url`), come fa il Finder: è ciò che legge Ableton.
- **Linux**: `text/uri-list` è il formato che chiede REAPER (SWELL/GDK) e
  che legge JUCE; lo scriviamo esplicito, terminato CRLF (RFC 2483).

I percorsi arrivano assoluti e normalizzati, senza il prefisso `\\\\?\\`
(le DAW non lo capiscono), e solo per file che esistono: la schermata
risultato appare dopo che il worker ha chiuso i file.
"""

from __future__ import annotations

import logging
import ntpath
import os
import posixpath
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl

log = logging.getLogger("stemforge")

URI_LIST = "text/uri-list"
# MAX_PATH conta anche il terminatore: oltre 259 caratteri una DAW non
# long-path-aware non apre il file.
WIN_MAX_PATH = 260
_VERBATIM = "\\\\?\\"
_VERBATIM_UNC = "\\\\?\\UNC\\"


def build_mime_data(paths: list[Path]) -> QMimeData:
    """MIME del drag per il sistema corrente. Senza file validi non ha URL:
    il chiamante controlla `hasUrls()` prima di avviare il drag."""
    return mime_for_platform(drop_paths(paths), sys.platform)


def mime_for_platform(files: list[str], platform: str) -> QMimeData:
    """Compone il MIME per `platform` da percorsi già normalizzati."""
    mime = QMimeData()
    if not files:
        return mime
    if platform == "win32":
        # in avanti: QUrl riconosce unità e UNC su qualunque host
        files = [name.replace("\\", "/") for name in files]
    urls = [QUrl.fromLocalFile(name) for name in files]
    mime.setUrls(urls)
    if platform not in ("win32", "darwin"):
        mime.setData(URI_LIST, uri_list_payload(urls))
    return mime


def uri_list_payload(urls: list[QUrl]) -> bytes:
    """RFC 2483: un URI codificato per riga, ogni riga chiusa da CRLF."""
    return b"".join(bytes(url.toEncoded()) + b"\r\n" for url in urls)


def drop_paths(paths: list[Path]) -> list[str]:
    """Percorsi assoluti dei file esistenti, nell'ordine dato, senza doppi."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = normalize_path(os.fspath(raw), sys.platform)
        if not _is_file(path):
            log.warning("drag: %s non esiste o non è un file, escluso", path)
            continue
        if sys.platform == "win32":
            path = fit_windows_max_path(path)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def normalize_path(raw: str, platform: str) -> str:
    """Assoluto, senza `..`, e su Windows senza prefisso verbatim."""
    if platform != "win32":
        return posixpath.normpath(posixpath.abspath(raw))
    path = strip_verbatim(raw.replace("/", "\\"))
    return ntpath.normpath(ntpath.abspath(path))


def strip_verbatim(path: str) -> str:
    """`\\\\?\\C:\\x` → `C:\\x`, `\\\\?\\UNC\\srv\\x` → `\\\\srv\\x`."""
    if path.upper().startswith(_VERBATIM_UNC):
        return "\\\\" + path[len(_VERBATIM_UNC):]
    if path.startswith(_VERBATIM):
        return path[len(_VERBATIM):]
    return path


def fit_windows_max_path(path: str) -> str:
    """Oltre MAX_PATH accorcia le cartelle con i nomi 8.3, mai il nome del
    file: la DAW chiama la traccia come il file (§7.3)."""
    if len(path) < WIN_MAX_PATH:
        return path
    parent, name = ntpath.split(path)
    candidate = ntpath.join(_short_path_name(parent), name)
    if len(candidate) < WIN_MAX_PATH:
        return candidate
    log.warning("drag: percorso oltre %d caratteri, la DAW potrebbe non aprirlo: %s",
                WIN_MAX_PATH - 1, path)
    return path


def _verbatim(path: str) -> str:
    if path.startswith("\\\\"):
        return _VERBATIM_UNC + path[2:]
    return _VERBATIM + path


def _is_file(path: str) -> bool:
    # il prefisso verbatim serve solo a noi per vedere i percorsi lunghi
    return os.path.isfile(_verbatim(path) if sys.platform == "win32" else path)


def _short_path_name(path: str) -> str:
    """GetShortPathNameW; se i nomi 8.3 sono disattivati torna `path`."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_short = kernel32.GetShortPathNameW
    get_short.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    get_short.restype = wintypes.DWORD
    source = _verbatim(path)
    needed = get_short(source, None, 0)
    if needed == 0:
        log.warning("drag: GetShortPathNameW fallita (%d) per %s",
                    ctypes.get_last_error(), path)
        return path
    buffer = ctypes.create_unicode_buffer(needed)
    if get_short(source, buffer, needed) == 0:
        return path
    return strip_verbatim(buffer.value)
