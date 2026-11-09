"""Schermata 4: risultato e drag out — la schermata che conta (§8.4).

Ogni riga è trascinabile e la selezione multipla si trascina in un colpo
solo (§7.2): l'azione è Copy, mai Move, con i percorsi assoluti di file
già chiusi. Preview: un solo stem alla volta, play/stop, niente mixer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDrag, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.model.manifest import Manifest

_PATH_ROLE = Qt.ItemDataRole.UserRole
_REVEAL_LABELS = {"darwin": "Mostra nel Finder", "win32": "Mostra in Esplora file"}


def _drag_pixmap(count: int) -> QPixmap:
    pixmap = QPixmap(56, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(Qt.GlobalColor.darkGray)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 55, 39, 8, 8)
    painter.setPen(Qt.GlobalColor.white)
    painter.setFont(QFont("", 14, QFont.Weight.Bold))
    label = f"♪ ×{count}" if count > 1 else "♪"
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    return pixmap


class StemList(QListWidget):
    """Lista con drag OUT multiplo (§7.2). Il drag parte anche quando la
    finestra non ha il fuoco: nessuno stato interno da preparare prima."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)

    def startDrag(self, _actions) -> None:
        paths = [
            item.data(_PATH_ROLE)
            for item in self.selectedItems()
            if item.data(_PATH_ROLE)
        ]
        if not paths:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        drag.setMimeData(mime)
        drag.setPixmap(_drag_pixmap(len(paths)))
        drag.setHotSpot(QPoint(28, 20))
        # Copy, mai Move: il file resta nella cartella di output (§7.2)
        drag.exec(Qt.DropAction.CopyAction)


class ResultView(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._out_dir: Path | None = None
        self._player = None  # creato pigramente: QtMultimedia pesa
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Trascina gli stem nel tuo progetto")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel("Selezionane più d'uno e trascinali insieme: Ableton crea una traccia per file.")
        hint.setObjectName("dim")
        layout.addWidget(hint)

        self.list = StemList()
        layout.addWidget(self.list, stretch=1)

        self._warnings = QLabel("")
        self._warnings.setObjectName("dim")
        self._warnings.setWordWrap(True)
        layout.addWidget(self._warnings)

        buttons = QHBoxLayout()
        self._play = QPushButton("▶ Ascolta")
        self._play.clicked.connect(self._toggle_preview)
        reveal = QPushButton(_REVEAL_LABELS.get(sys.platform, "Mostra nella cartella"))
        reveal.clicked.connect(self._reveal)
        again = QPushButton("Un altro brano")
        again.clicked.connect(self.back_requested.emit)
        buttons.addWidget(self._play)
        buttons.addWidget(reveal)
        buttons.addStretch(1)
        buttons.addWidget(again)
        layout.addLayout(buttons)

    # -- popolamento ------------------------------------------------------

    def show_result(self, out_dir: Path, manifest_path: Path, warnings: list[str]) -> None:
        self._stop_preview()
        self._out_dir = out_dir
        self.list.clear()
        manifest = Manifest.from_json(manifest_path.read_text(encoding="utf-8"))
        minutes, seconds = divmod(round(manifest.source.duration_s), 60)
        for stem in manifest.stems:
            item = QListWidgetItem(
                f"{stem.file}    ·    {minutes}:{seconds:02d}    ·    picco {stem.peak_dbfs:.1f} dBFS"
            )
            item.setData(_PATH_ROLE, out_dir / stem.file)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._warnings.setText("\n".join(warnings))

    # -- preview: un solo stem alla volta (§8.4) --------------------------

    def _toggle_preview(self) -> None:
        if self._player is not None and self._is_playing():
            self._stop_preview()
            return
        item = self.list.currentItem()
        if item is None or not item.data(_PATH_ROLE):
            return
        self._ensure_player()
        self._player.setSource(QUrl.fromLocalFile(str(item.data(_PATH_ROLE))))
        self._player.play()
        self._play.setText("■ Stop")

    def _ensure_player(self) -> None:
        if self._player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.playbackStateChanged.connect(self._on_playback_state)

    def _is_playing(self) -> bool:
        from PySide6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _stop_preview(self) -> None:
        if self._player is not None:
            self._player.stop()
        self._play.setText("▶ Ascolta")

    def _on_playback_state(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._play.setText("▶ Ascolta")

    # -- rivelazione (§7.4) ------------------------------------------------

    def _reveal(self) -> None:
        item = self.list.currentItem()
        target = item.data(_PATH_ROLE) if item else self._out_dir
        if target is None:
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(Path(target).parent)])
