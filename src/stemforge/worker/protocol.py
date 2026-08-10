"""Protocollo JSON-lines fra UI e worker (BUILD_SPEC D2).

Unica definizione dei messaggi: UI (bridge.py) e worker (runner.py)
importano entrambi da qui. Un oggetto JSON per riga su stdout del
figlio; lo stdin riceve il SeparationJob serializzato e nient'altro.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class Started:
    """Il worker ha allocato la cartella: il padre la può ripulire
    se l'utente annulla (§8.3)."""

    out_dir: str


@dataclass(frozen=True)
class Phase:
    label: str  # "Separazione — passata 2 di 3", "Scrittura stem"...
    pass_index: int  # 1-based
    pass_count: int


@dataclass(frozen=True)
class Progress:
    value: float  # 0.0-1.0 globale, già pesato sui costi (§8.3)


@dataclass(frozen=True)
class Warning_:
    message: str  # avviso non bloccante (§5.2.4, traccia silenziosa...)


@dataclass(frozen=True)
class Done:
    out_dir: str
    manifest: str


@dataclass(frozen=True)
class Error:
    message: str  # per l'utente: dice cosa fare (§10.1)
    detail: str  # per il log: traceback completo


Message = Started | Phase | Progress | Warning_ | Done | Error

_TYPES: dict[str, type] = {
    "started": Started,
    "phase": Phase,
    "progress": Progress,
    "warning": Warning_,
    "done": Done,
    "error": Error,
}
_NAMES = {cls: name for name, cls in _TYPES.items()}


def encode(message: Message) -> str:
    payload = {"type": _NAMES[type(message)], **message.__dict__}
    return json.dumps(payload)


def decode(line: str) -> Message | None:
    """None per righe non-protocollo (rumore di librerie su stdout)."""
    line = line.strip()
    if not line or not line.startswith("{"):
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    cls = _TYPES.get(payload.pop("type", None))
    if cls is None:
        return None
    try:
        return cls(**payload)
    except TypeError:
        return None


def write_message(stream: TextIO, message: Message) -> None:
    stream.write(encode(message) + "\n")
    stream.flush()
