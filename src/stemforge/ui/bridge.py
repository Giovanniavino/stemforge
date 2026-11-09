"""Bridge QProcess <-> worker: l'unico interlocutore dei widget (§8.5).

BUILD_SPEC D2. Lancia il processo figlio, gli scrive il job su stdin,
traduce le JSON-lines di stdout in segnali Qt. Annullare = uccidere il
figlio e ripulire la cartella annunciata da `Started`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from stemforge.model.job import SeparationJob
from stemforge.worker import protocol
from stemforge.worker.launch import worker_command


class WorkerBridge(QObject):
    started = Signal(str)  # out_dir allocata
    phase = Signal(str, int, int)  # label, indice, totale
    progress = Signal(float)  # 0.0-1.0 globale
    warning = Signal(str)
    done = Signal(str, str)  # out_dir, manifest
    failed = Signal(str, str)  # messaggio utente, dettaglio per il log
    cancelled = Signal()

    _STDERR_TAIL = 16_384  # basta per un traceback completo nel log

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._out_dir: Path | None = None
        self._buffer = ""
        self._stderr_tail = ""
        self._cancelling = False
        self._error_reported = False

    # -- avvio ------------------------------------------------------------

    def start_job(self, job: SeparationJob) -> None:
        assert self._process is None, "un job alla volta"
        self._out_dir = None
        self._cancelling = False
        self._process = self._spawn(extra_args=[])
        self._process.write((job.to_json() + "\n").encode("utf-8"))

    def start_prepare(self) -> None:
        """Primo avvio: download pesi + calibrazione (§9.4)."""
        assert self._process is None, "un job alla volta"
        self._cancelling = False
        self._process = self._spawn(extra_args=["--prepare"])

    def _spawn(self, extra_args: list[str]) -> QProcess:
        process = QProcess(self)
        command = worker_command()
        process.setProgram(command[0])
        process.setArguments(command[1:] + extra_args)
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)
        self._stderr_tail = ""
        self._error_reported = False
        process.start()
        return process

    # -- annullo ----------------------------------------------------------

    def cancel(self) -> None:
        """Uccide il figlio (la garanzia del secondo, §5.5) e ripulisce."""
        if self._process is None:
            return
        self._cancelling = True
        self._process.kill()

    @property
    def running(self) -> bool:
        return self._process is not None

    # -- protocollo -------------------------------------------------------

    def _on_stdout(self) -> None:
        assert self._process is not None
        # bytes(...) e non toStdString(): deve girare anche su PySide6 6.4,
        # l'ultima disponibile per il target macOS 10.15 (§2)
        raw = self._process.readAllStandardOutput()
        self._buffer += bytes(raw).decode("utf-8", errors="replace")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            message = protocol.decode(line)
            if message is not None:
                self._dispatch(message)

    def _on_stderr(self) -> None:
        # senza questo, il traceback di un crash duro del figlio sparirebbe:
        # e' l'unica prova di cosa e' successo davvero (§10.1)
        assert self._process is not None
        raw = self._process.readAllStandardError()
        self._stderr_tail += bytes(raw).decode("utf-8", errors="replace")
        self._stderr_tail = self._stderr_tail[-self._STDERR_TAIL:]

    def _dispatch(self, message: protocol.Message) -> None:
        if isinstance(message, protocol.Started):
            self._out_dir = Path(message.out_dir)
            self.started.emit(message.out_dir)
        elif isinstance(message, protocol.Phase):
            self.phase.emit(message.label, message.pass_index, message.pass_count)
        elif isinstance(message, protocol.Progress):
            self.progress.emit(message.value)
        elif isinstance(message, protocol.Warning_):
            self.warning.emit(message.message)
        elif isinstance(message, protocol.Done):
            self.done.emit(message.out_dir, message.manifest)
        elif isinstance(message, protocol.Error):
            self._error_reported = True
            self.failed.emit(message.message, message.detail)

    def _on_finished(self, exit_code: int, _status: object) -> None:
        process, self._process = self._process, None
        if process is not None:
            process.deleteLater()
        if self._cancelling:
            self._cleanup_partials()
            self.cancelled.emit()
            return
        if self._error_reported:
            # il figlio ha già spiegato cosa è successo: il fallback
            # generico qui sotto lo SOVRASCRIVEREBBE nell'UI
            return
        if exit_code not in (0, None):
            # il figlio è morto senza un messaggio Error (crash duro)
            detail = f"exit code {exit_code}"
            if self._stderr_tail.strip():
                detail += "\n--- stderr del worker ---\n" + self._stderr_tail
            self.failed.emit(
                "Il processo di separazione si è interrotto. "
                "Riprova; se succede ancora, guarda il log.",
                detail,
            )

    def _cleanup_partials(self) -> None:
        """§8.3: annullare cancella i file parziali del job."""
        if self._out_dir is not None and self._out_dir.exists():
            shutil.rmtree(self._out_dir, ignore_errors=True)
        self._out_dir = None
