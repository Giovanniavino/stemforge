"""Errori del motore che arrivano all'utente (BUILD_SPEC §10.1, §8.6).

Il motore non conosce le lingue: un errore per l'utente porta una
CHIAVE del catalogo di worker/i18n.py più i parametri, e chi lo mostra
(worker, CLI) lo traduce nella lingua del processo. Così non esiste un
italiano a metà in un'interfaccia inglese, e il testo tecnico per il
log (`detail`) resta separato da quello che dice all'utente cosa fare.
"""

from __future__ import annotations


class UserFacingError(Exception):
    """Errore con un testo per l'utente: `key` del catalogo e `params`."""

    def __init__(self, key: str, detail: str = "", **params: object) -> None:
        self.key = key
        self.params = params
        self.detail = detail
        shown = ", ".join(f"{name}={value!r}" for name, value in params.items())
        super().__init__(f"{key}({shown})" + (f": {detail}" if detail else ""))


class InsufficientDiskError(UserFacingError, RuntimeError):
    """Il controllo PRIMA di iniziare (§10.1) dice che lo spazio non basta.

    Il disco che si riempie DURANTE la scrittura arriva invece come
    OSError(ENOSPC) da export/folder.py, che non importa engine (§3).
    """
