"""Screen reader (VoiceOver, NVDA): nomi accessibili e annunci (§8.6).

Gli annunci servono per ciò che cambia senza che l'utente sposti il
focus: la fase dell'avanzamento, l'esito di un job, un file rifiutato.
Da Qt 6.8 esiste QAccessibleAnnouncementEvent, fatto apposta; su Qt 6.4
(profilo legacy-intel) si aggiorna la descrizione del widget e si manda
un evento Alert, che NVDA e VoiceOver leggono come notifica.
"""

from __future__ import annotations

from PySide6 import QtGui
from PySide6.QtGui import QAccessible, QAccessibleEvent
from PySide6.QtWidgets import QWidget


def name(widget: QWidget, accessible_name: str, description: str = "") -> None:
    """Nome (cosa è) e descrizione (cosa fa) per lo screen reader.

    Il testo visibile può contenere simboli decorativi (▶, 🎤): il nome
    accessibile no, altrimenti VoiceOver legge "microfono Voce".
    """
    widget.setAccessibleName(accessible_name)
    widget.setAccessibleDescription(description)


def announce(source: QWidget, message: str) -> None:
    if not message:
        return
    announcement = getattr(QtGui, "QAccessibleAnnouncementEvent", None)
    if announcement is not None:
        _send(announcement(source, message))
        return
    source.setAccessibleDescription(message)
    _send(QAccessibleEvent(source, QAccessible.Event.DescriptionChanged))
    _send(QAccessibleEvent(source, QAccessible.Event.Alert))


def _send(event: QAccessibleEvent) -> None:
    # un solo punto d'uscita: i test lo sostituiscono per vedere gli annunci
    QAccessible.updateAccessibility(event)
