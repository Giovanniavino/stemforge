"""Da un'eccezione al testo per l'utente, nella sua lingua (§10.1, §8.6).

Un solo posto decide cosa vede l'utente quando qualcosa va storto:
runner (il processo figlio) e CLI chiamano user_message() e mettono il
traceback nel log, mai sullo schermo (§10.1 regola 2). Ogni testo dice
cosa fare: "Errore di separazione" non esiste.
"""

from __future__ import annotations

import errno

from stemforge.engine.contract import BackendUnavailable
from stemforge.engine.errors import UserFacingError, is_memory_error
from stemforge.worker.i18n import t

# Windows riporta il disco pieno come winerror 112 (ERROR_DISK_FULL) o
# 39 (ERROR_HANDLE_DISK_FULL); Python di solito lo traduce in ENOSPC,
# ma non per ogni chiamata.
_WIN_DISK_FULL = frozenset({39, 112})


def is_disk_full(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    return exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in _WIN_DISK_FULL


def user_message(exc: BaseException) -> str:
    """Il messaggio da mostrare per un job fallito."""
    if isinstance(exc, UserFacingError):
        return t(exc.key, **exc.params)
    if is_memory_error(exc):
        return t("err.memory")
    if is_disk_full(exc):
        return t("err.disk_full")
    if isinstance(exc, BackendUnavailable):
        return t("err.model_unavailable")
    return t("err.generic")


def prepare_message(exc: BaseException) -> str:
    """Messaggio per un primo avvio fallito (§9.4)."""
    import socket
    import urllib.error

    if isinstance(exc, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
        return t("prepare.offline")
    if isinstance(exc, BackendUnavailable) and isinstance(exc.__cause__, (OSError, urllib.error.URLError)):
        return prepare_message(exc.__cause__)
    if is_disk_full(exc):
        return t("prepare.disk")
    return t("prepare.generic")
