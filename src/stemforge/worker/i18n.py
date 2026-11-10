"""Testi del worker per l'utente, in italiano e inglese (BUILD_SPEC §8.6).

I messaggi d'errore, gli avvisi e le etichette di fase arrivano all'UI
GIÀ TRADOTTI: mai un italiano a metà in un'interfaccia inglese. La
lingua la sceglie chi lancia il processo, con la variabile d'ambiente
STEMFORGE_LOCALE ("it" | "en"): il bridge dell'UI la imposta sul figlio,
la CLI da --lang o dalla lingua del sistema. Nessun campo nel
SeparationJob: la lingua è dell'ambiente, non della richiesta.

La lingua si rilegge a ogni chiamata invece di stare in un modulo-stato
(§11 regola 6): il costo è una lettura di os.environ.
"""

from __future__ import annotations

import locale
import logging
import os
from typing import Mapping

from stemforge.worker import catalog

log = logging.getLogger(__name__)

LOCALE_ENV = "STEMFORGE_LOCALE"
DEFAULT_LOCALE = "it"
LOCALES = ("it", "en")

_CATALOGS: dict[str, dict[str, str]] = {"it": catalog.IT, "en": catalog.EN}


def normalize(raw: str | None) -> str | None:
    """"it_IT.UTF-8", "Italian_Italy", "en-GB" -> "it"/"en"; altro -> None."""
    if not raw:
        return None
    value = raw.strip().lower()
    if value.startswith(("it", "italian")):
        return "it"
    if value.startswith(("en", "english")):
        return "en"
    return None


def current_locale() -> str:
    return normalize(os.environ.get(LOCALE_ENV)) or DEFAULT_LOCALE


def system_locale(env: Mapping[str, str] | None = None) -> str:
    """Lingua del sistema per la CLI: italiano se il sistema è italiano,
    inglese per ogni altra lingua (è la lingua franca, §8.6).

    Decide la prima variabile POSIX valorizzata, come fa libc: un
    LC_ALL=fr_FR vince su LANG=it_IT. "C"/"POSIX" non dicono una lingua.
    """
    environ = os.environ if env is None else env
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (environ.get(var) or "").strip()
        if value and value.split(".")[0].upper() not in ("C", "POSIX"):
            return normalize(value) or "en"
    try:
        code = locale.getlocale()[0]
    except ValueError:  # locale malformato nell'ambiente: vale come "altro"
        code = None
    return normalize(code) or "en"


def t(key: str, **params: object) -> str:
    """Testo per l'utente nella lingua corrente; l'italiano fa da riserva.

    Non solleva mai: un errore nel tradurre un errore nasconderebbe
    all'utente quello vero. Una chiave o un parametro mancanti sono
    bachi che i test del catalogo intercettano; qui finiscono nel log.
    """
    table = _CATALOGS.get(current_locale(), catalog.IT)
    template = table.get(key) or catalog.IT.get(key)
    if template is None:
        log.error("chiave di traduzione sconosciuta: %s", key)
        return key
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        log.exception("parametri mancanti per %s: %r", key, params)
        return template
