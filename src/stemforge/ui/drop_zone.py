"""Schermata 1: la zona di drop (BUILD_SPEC §8.1), con in fondo i due
controlli discreti di lingua e diagnostica (§8.6, §9.9)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QCoreApplication, QEvent, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.ui import a11y, conventions
from stemforge.ui.home_footer import HomeFooter
from stemforge.worker.planning import SUPPORTED_SUFFIXES, is_supported

translate = QCoreApplication.translate


def _file_filter() -> str:
    patterns = " ".join(f"*{s}" for s in sorted(SUPPORTED_SUFFIXES))
    return translate("DropZone", "Audio ({patterns})").format(patterns=patterns)


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


def _rejected_text(count: int) -> str:
    if count == 1:
        return translate("DropZone", "1 file ignored (not audio).")
    return translate("DropZone", "{count} files ignored (not audio).").format(count=count)


class DropZone(QWidget):
    files_chosen = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        # il messaggio si ricalcola al cambio di lingua: mai un avviso
        # rimasto nella lingua di prima (§8.6)
        self._message_source: Callable[[], str] = lambda: ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 24)

        self._frame = QFrame()
        self._frame.setObjectName("dropzone")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.setSpacing(16)

        self._title = QLabel()
        self._title.setObjectName("title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._subtitle = QLabel()
        self._subtitle.setObjectName("dim")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.choose_button = QPushButton()
        self.choose_button.clicked.connect(self.choose_files)

        self._message = QLabel("")
        self._message.setObjectName("error")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)

        frame_layout.addStretch(1)
        frame_layout.addWidget(self._title)
        frame_layout.addWidget(self._subtitle)
        frame_layout.addWidget(self.choose_button, alignment=Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(self._message)
        frame_layout.addStretch(1)
        layout.addWidget(self._frame, stretch=1)

        self.footer = HomeFooter()
        layout.addWidget(self.footer)
        self._retranslate()

    def show_error(self, message: str) -> None:
        """Messaggio inline (es. primo avvio fallito), schermata usabile."""
        self._set_message(lambda: message)

    def _set_message(self, source: Callable[[], str]) -> None:
        self._message_source = source
        text = source()
        self._message.setText(text)
        a11y.announce(self._message, text)

    # -- lingua -----------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def _retranslate(self) -> None:
        self._title.setText(translate("DropZone", "Drag a song here"))
        self._subtitle.setText(translate("DropZone", "or"))
        self.choose_button.setText(translate("DropZone", "Choose a file…"))
        shortcut = conventions.shortcut_text(QKeySequence.StandardKey.Open)
        a11y.name(
            self.choose_button,
            translate("DropZone", "Choose a file"),
            translate("DropZone", "Opens the file chooser ({shortcut}). Folders and several files are accepted too.").format(shortcut=shortcut),
        )
        self.choose_button.setToolTip(shortcut)
        self._message.setText(self._message_source())

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

    def choose_files(self) -> None:
        """Pulsante e Cmd/Ctrl+O (§8.6)."""
        names, _ = QFileDialog.getOpenFileNames(
            self, translate("DropZone", "Choose a song"), "", _file_filter()
        )
        if names:
            self._accept([Path(n) for n in names])

    def accept_paths(self, paths: list[Path]) -> None:
        """File arrivati da fuori (Apri con, riga di comando): stesso filtro del drop."""
        self._accept(paths)

    def _accept(self, paths: list[Path]) -> None:
        accepted, rejected = _collect_audio_files(paths)
        if rejected and not accepted:
            # messaggio inline, nessun dialog modale (§8.1)
            self._set_message(lambda: translate("DropZone", "This is not an audio file I know."))
            return
        if rejected:
            self._set_message(lambda: _rejected_text(rejected))
        else:
            self._set_message(lambda: "")
        if accepted:
            self.files_chosen.emit(accepted)
