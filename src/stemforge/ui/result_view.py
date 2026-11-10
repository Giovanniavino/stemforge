"""Schermata 4: risultato e drag out — la schermata che conta (§8.4).

Ogni riga è trascinabile e la selezione multipla si trascina in un colpo
solo (§7.2): l'azione è Copy, mai Move, con i percorsi assoluti di file
già chiusi. Il contenuto del drag (formati per sistema e DAW) lo
costruisce ui/drag_export.py. Preview: un solo stem alla volta,
play/stop, niente mixer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QLocale, QPoint, Qt, QUrl, Signal
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
from stemforge.ui import a11y, conventions, i18n

translate = QCoreApplication.translate

_PATH_ROLE = Qt.ItemDataRole.UserRole
_PIXMAP_SIZE = (56, 40)
_PIXMAP_FONT_PT = 14


def _drag_pixmap(count: int) -> QPixmap:
    width, height = _PIXMAP_SIZE
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setBrush(Qt.GlobalColor.darkGray)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, width - 1, height - 1, 8, 8)
    painter.setPen(Qt.GlobalColor.white)
    painter.setFont(QFont("", _PIXMAP_FONT_PT, QFont.Weight.Bold))
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

    def selected_paths(self) -> list[Path]:
        return [
            Path(item.data(_PATH_ROLE))
            for item in self.selectedItems()
            if item.data(_PATH_ROLE)
        ]

    def startDrag(self, _actions) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        # import pigro: il modulo è dell'area DAW (§7.2) e decide i
        # formati del drag per ogni sistema; qui si sceglie solo cosa
        from stemforge.ui.drag_export import build_mime_data

        drag = QDrag(self)
        drag.setMimeData(build_mime_data(paths))
        drag.setPixmap(_drag_pixmap(len(paths)))
        drag.setHotSpot(QPoint(_PIXMAP_SIZE[0] // 2, _PIXMAP_SIZE[1] // 2))
        # Copy, mai Move: il file resta nella cartella di output (§7.2)
        drag.exec(Qt.DropAction.CopyAction)


class ResultView(QWidget):
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._out_dir: Path | None = None
        self._manifest: Manifest | None = None
        self._player = None  # creato pigramente: QtMultimedia pesa
        self._playing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        self._title = QLabel()
        self._title.setObjectName("title")
        self._title.setWordWrap(True)
        layout.addWidget(self._title)
        self._hint = QLabel()
        self._hint.setObjectName("dim")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self.list = StemList()
        layout.addWidget(self.list, stretch=1)

        self._warnings = QLabel("")
        self._warnings.setObjectName("dim")
        self._warnings.setWordWrap(True)
        layout.addWidget(self._warnings)

        buttons = QHBoxLayout()
        self._play = QPushButton()
        self._play.clicked.connect(self._toggle_preview)
        self._reveal_button = QPushButton()
        self._reveal_button.clicked.connect(self._reveal)
        self._again = QPushButton()
        self._again.clicked.connect(self.back_requested.emit)
        buttons.addWidget(self._play)
        buttons.addWidget(self._reveal_button)
        buttons.addStretch(1)
        buttons.addWidget(self._again)
        layout.addLayout(buttons)
        self._retranslate()

    # -- lingua -----------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def _retranslate(self) -> None:
        self._title.setText(translate("ResultView", "Drag the stems into your project"))
        self._hint.setText(translate(
            "ResultView",
            "Select more than one and drag them together: Ableton creates one track per file.",
        ))
        a11y.name(
            self.list, translate("ResultView", "Stems"),
            translate("ResultView", "Select one or more stems and drag them into the DAW."),
        )
        reveal = conventions.reveal_label()
        self._reveal_button.setText(reveal)
        a11y.name(self._reveal_button, reveal,
                  translate("ResultView", "Opens the folder with the selected stem highlighted."))
        self._again.setText(translate("ResultView", "Another song"))
        a11y.name(self._again, translate("ResultView", "Another song"),
                  translate("ResultView", "Back to choosing a song (Esc)."))
        self._update_play_button()
        self._fill_rows()

    def _update_play_button(self) -> None:
        if self._playing:
            label = translate("ResultView", "Stop")
            self._play.setText("■ " + label)
        else:
            label = translate("ResultView", "Listen")
            self._play.setText("▶ " + label)
        a11y.name(self._play, label,
                  translate("ResultView", "Plays the selected stem, one at a time."))

    # -- popolamento ------------------------------------------------------

    def show_result(self, out_dir: Path, manifest_path: Path, warnings: list[str]) -> None:
        self._stop_preview()
        self._out_dir = out_dir
        self._manifest = Manifest.from_json(manifest_path.read_text(encoding="utf-8"))
        self.list.clear()
        for stem in self._manifest.stems:
            item = QListWidgetItem()
            item.setData(_PATH_ROLE, out_dir / stem.file)
            self.list.addItem(item)
        self._fill_rows()
        if self.list.count():
            self.list.setCurrentRow(0)
        self._warnings.setText("\n".join(warnings))
        count = self.list.count()
        if count == 1:
            done = translate("ResultView", "Separation finished: 1 stem ready.")
        else:
            done = translate("ResultView", "Separation finished: {count} stems ready.")
        a11y.announce(self._title, done.format(count=count))

    def _fill_rows(self) -> None:
        """Testo delle righe nella lingua attiva, numeri compresi (-1,0 / -1.0)."""
        if self._manifest is None:
            return
        locale = QLocale(i18n.active_language())
        minutes, seconds = divmod(round(self._manifest.source.duration_s), 60)
        for row, stem in enumerate(self._manifest.stems):
            item = self.list.item(row)
            if item is None:
                return
            peak = locale.toString(float(stem.peak_dbfs), "f", 1)
            item.setText(translate(
                "ResultView", "{file}    ·    {duration}    ·    peak {peak} dBFS"
            ).format(file=stem.file, duration=f"{minutes}:{seconds:02d}", peak=peak))

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
        self._playing = True
        self._update_play_button()

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
        self._playing = False
        self._update_play_button()

    def _on_playback_state(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._playing = False
            self._update_play_button()

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

    def initial_focus(self) -> QWidget:
        return self.list
