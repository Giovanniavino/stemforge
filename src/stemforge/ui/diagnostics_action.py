"""Esporta diagnostica (BUILD_SPEC §9.9): niente telemetria, uno zip
salvato dove sceglie l'utente, che decide se e a chi mandarlo.

Lo zip lo prepara `stemforge.worker.diagnostics.export_diagnostics`
(log, versione, sistema, `--selftest --offline`): può richiedere
qualche secondo, quindi gira in un thread Python e l'esito torna con
un segnale Qt. Non è inferenza: la regola "niente QThread per
l'inferenza" (§8.5) non c'entra.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QFileDialog, QWidget

translate = QCoreApplication.translate
log = logging.getLogger("stemforge")


def ask_folder(parent: QWidget) -> Path | None:
    chosen = QFileDialog.getExistingDirectory(
        parent, translate("Diagnostics", "Where should the diagnostics be saved?")
    )
    return Path(chosen) if chosen else None


class DiagnosticsExporter(QObject):
    busy = Signal()
    succeeded = Signal(str)  # percorso dello zip
    failed = Signal(str)  # messaggio per l'utente

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def export(self, parent: QWidget) -> None:
        """Il gestore del pulsante e della voce del menu Aiuto."""
        if self.running:
            return
        try:
            # import pigro: il modulo vive nel worker (area E) e porta con
            # sé il collaudo, che non serve finché nessuno lo chiede
            from stemforge.worker.diagnostics import export_diagnostics
        except ImportError:
            log.exception("diagnostica non disponibile")
            self.failed.emit(translate(
                "Diagnostics", "Diagnostics export is not available in this version."
            ))
            return
        dest = ask_folder(parent)
        if dest is None:
            return
        self.busy.emit()
        self._thread = threading.Thread(
            target=self._run, args=(export_diagnostics, dest), daemon=True
        )
        self._thread.start()

    def wait(self, timeout_s: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout_s)

    def _run(self, export_diagnostics, dest: Path) -> None:
        try:
            archive = export_diagnostics(dest)
        except Exception as exc:  # qualunque errore va mostrato, non perso
            log.exception("esportazione della diagnostica fallita")
            self.failed.emit(translate(
                "Diagnostics", "Could not export the diagnostics: {error}"
            ).format(error=exc))
            return
        log.info("diagnostica esportata in %s", archive)
        self.succeeded.emit(str(archive))
