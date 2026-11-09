"""Schermata 1: la zona di drop (BUILD_SPEC §8.1)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.worker.planning import SUPPORTED_SUFFIXES, is_supported

_FILE_FILTER = "Audio (" + " ".join(f"*{s}" for s in sorted(SUPPORTED_SUFFIXES)) + ")"


def _collect_audio_files(paths: list[Path]) -> tuple[list[Path], int]:
    """File audio validi (cartelle incluse, §8.1) e quanti scartati."""
    accepted: list[Path] = []
    rejected = 0
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    if is_supported(child):
                        accepted.append(child)
                    else:
                        rejected += 1
        elif is_supported(path):
            accepted.append(path)
        else:
            rejected += 1
    return accepted, rejected


class DropZone(QWidget):
    files_chosen = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        self._frame = QFrame()
        self._frame.setObjectName("dropzone")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.setSpacing(16)

        title = QLabel("Trascina un brano")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("oppure")
        subtitle.setObjectName("dim")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        choose = QPushButton("Scegli un file…")
        choose.clicked.connect(self._choose_files)

        self._message = QLabel("")
        self._message.setObjectName("error")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        frame_layout.addStretch(1)
        frame_layout.addWidget(title)
        frame_layout.addWidget(subtitle)
        frame_layout.addWidget(choose, alignment=Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self._message)
        frame_layout.addStretch(1)
        layout.addWidget(self._frame)

    def show_error(self, message: str) -> None:
        """Messaggio inline (es. primo avvio fallito), schermata usabile."""
        self._message.setText(message)

    # -- drag & drop in ingresso ------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self._set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        self._accept(paths)
        event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        self._frame.setProperty("dragActive", "true" if active else "false")
        self._frame.style().unpolish(self._frame)
        self._frame.style().polish(self._frame)

    # -- selezione --------------------------------------------------------

    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Scegli un brano", "", _FILE_FILTER)
        if names:
            self._accept([Path(n) for n in names])

    def accept_paths(self, paths: list[Path]) -> None:
        """File arrivati da fuori (Apri con, riga di comando): stesso filtro del drop."""
        self._accept(paths)

    def _accept(self, paths: list[Path]) -> None:
        accepted, rejected = _collect_audio_files(paths)
        if rejected and not accepted:
            # messaggio inline, nessun dialog modale (§8.1)
            self._message.setText("Questo non è un file audio che conosco.")
            return
        if rejected:
            self._message.setText(f"{rejected} file ignorati (non sono audio).")
        else:
            self._message.setText("")
        if accepted:
            self.files_chosen.emit(accepted)
