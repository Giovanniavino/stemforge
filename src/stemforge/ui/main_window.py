"""Shell e routing fra le quattro schermate (§8).

Coda dei file: più file trascinati si elaborano in sequenza con le
stesse scelte; un file che fallisce non ferma gli altri (§10.1).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from stemforge.model.job import SeparationJob
from stemforge.ui.bridge import WorkerBridge
from stemforge.ui.drop_zone import DropZone
from stemforge.ui.progress_view import ProgressView
from stemforge.ui.result_view import ResultView
from stemforge.ui.stem_picker import StemPicker
from stemforge.worker import planning

log = logging.getLogger("stemforge")


class MainWindow(QMainWindow):
    def __init__(self, out_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("StemForge")
        self.resize(760, 620)

        self._queue: list[Path] = []
        self._current_job: SeparationJob | None = None
        self._failures: list[str] = []
        self._warnings: list[str] = []
        self._preparing = False

        self._bridge = WorkerBridge(self)
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._drop = DropZone()
        self._picker = StemPicker(out_dir)
        self._progress = ProgressView()
        self._result = ResultView()
        for widget in (self._drop, self._picker, self._progress, self._result):
            self._stack.addWidget(widget)

        self._drop.files_chosen.connect(self._on_files)
        self._picker.start_requested.connect(self._on_start)
        self._progress.cancel_button.clicked.connect(self._bridge.cancel)
        self._result.back_requested.connect(self._show_drop)

        self._bridge.phase.connect(self._progress.set_phase)
        self._bridge.progress.connect(self._progress.set_progress)
        self._bridge.warning.connect(self._on_warning)
        self._bridge.done.connect(self._on_done)
        self._bridge.failed.connect(self._on_failed)
        self._bridge.cancelled.connect(self._on_cancelled)

    # -- prepare (primo avvio, §9.4) --------------------------------------

    def run_first_start_if_needed(self) -> None:
        if planning.prepared_marker().exists():
            self._show_drop()
            return
        self._preparing = True
        self._progress.reset()
        self._progress.cancel_button.setVisible(False)
        self._stack.setCurrentWidget(self._progress)
        self._bridge.start_prepare()

    def _end_prepare(self) -> None:
        self._preparing = False
        self._progress.cancel_button.setVisible(True)
        self._progress.stop()

    def _open_pending_after_prepare(self) -> None:
        """File aperti con "Apri con" mentre si scaricavano i modelli."""
        if self._queue and self._current_job is None:
            pending, self._queue = self._queue, []
            self._drop.accept_paths(pending)

    # -- file dall'esterno: "Apri con" del Finder / Esplora file (§9.1) ---

    def open_files(self, paths: list[Path]) -> None:
        audio = [p for p in paths if p.is_dir() or planning.is_supported(p)]
        if not audio:
            return
        if self._bridge.running or self._preparing:
            # un job è in corso: i nuovi file entrano in coda con le stesse
            # scelte, come un batch (§10.1), senza interrompere niente
            self._queue.extend(p for p in audio if p.is_file())
            return
        self._show_drop()
        self._drop.accept_paths(audio)
        self.raise_()
        self.activateWindow()

    # -- routing ----------------------------------------------------------

    def _show_drop(self) -> None:
        self._stack.setCurrentWidget(self._drop)

    def _on_files(self, paths: list[Path]) -> None:
        self._queue = list(paths)
        self._failures = []
        first = self._queue.pop(0)
        self._picker.set_source(first, planning.probe_duration(first))
        self._stack.setCurrentWidget(self._picker)

    def _on_start(self, job: SeparationJob) -> None:
        self._current_job = job
        self._warnings = []
        self._progress.reset()
        self._stack.setCurrentWidget(self._progress)
        log.info("job: %s -> %s", job.source.name, [k.value for k in job.wanted])
        self._bridge.start_job(job)

    # -- esiti ------------------------------------------------------------

    def _on_warning(self, message: str) -> None:
        self._warnings.append(message)
        self._progress.add_warning(message)
        log.warning("%s", message)

    def _on_done(self, out_dir: str, manifest: str) -> None:
        if self._preparing:
            self._end_prepare()
            self._show_drop()
            self._open_pending_after_prepare()
            return
        self._progress.stop()
        notes = list(self._warnings)
        if self._failures:
            notes.append("Errori nel batch: " + "; ".join(self._failures))
        self._result.show_result(Path(out_dir), Path(manifest), notes)
        self._stack.setCurrentWidget(self._result)
        self._start_next_in_queue()

    def _on_failed(self, message: str, detail: str) -> None:
        self._progress.stop()
        log.error("job fallito: %s\n%s", message, detail)
        if self._preparing:
            # il primo avvio fallito NON blocca l'app: si mostra la drop
            # zone con il motivo, e la preparazione riparte al prossimo
            # avvio perché il marker non esiste (§9.4, §10.1)
            self._end_prepare()
            self._drop.show_error(message)
            self._show_drop()
            self._open_pending_after_prepare()
            return
        self._failures.append(message)
        if self._queue:
            self._start_next_in_queue()
            return
        if self._current_job is None:
            # errore senza nessun job in corso: il picker non ha un file,
            # sarebbe un vicolo cieco — si va alla drop zone
            self._drop.show_error(message)
            self._show_drop()
            return
        # niente in coda: si torna alla scelta con le opzioni intatte (§10.1)
        self._picker.set_source_error(message)
        self._stack.setCurrentWidget(self._picker)

    def _on_cancelled(self) -> None:
        # §8.3: si torna alla schermata 2 con le scelte intatte
        self._progress.stop()
        self._queue = []
        self._stack.setCurrentWidget(self._picker)

    def _start_next_in_queue(self) -> None:
        if not self._queue or self._current_job is None:
            return
        source = self._queue.pop(0)
        template = self._current_job
        job = SeparationJob(
            source=source,
            wanted=template.wanted,
            quality=template.quality,
            out_dir=template.out_dir,
            fmt=template.fmt,
            device=template.device,
            dereverb_vocals=template.dereverb_vocals,
        )
        self._current_job = job
        log.info("batch: prossimo file %s", source.name)
        self._bridge.start_job(job)
