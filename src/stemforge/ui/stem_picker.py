"""Schermata 2: scelta strumenti e stima viva del tempo (§8.2).

La schermata dove l'utente decide quanto tempo vuole spendere: la stima
scende visibilmente quando si toglie roba — è il feedback che insegna
che chiedere meno costa meno (§8.2.1).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind
from stemforge.ui.stem_group import StemGroup
from stemforge.worker import planning

_BASE_CARDS: list[tuple[StemKind, str]] = [
    (StemKind.VOCALS, "🎤  Voce"),
    (StemKind.DRUMS, "🥁  Batteria"),
    (StemKind.BASS, "🎸  Basso"),
    (StemKind.GUITAR, "🎸  Chitarra"),
    (StemKind.PIANO, "🎹  Piano"),
    (StemKind.OTHER, "🎼  Altro"),
    (StemKind.INSTRUMENTAL, "🎛  Strumentale"),
]
_DEFAULT_CHECKED = {StemKind.VOCALS, StemKind.DRUMS, StemKind.BASS, StemKind.OTHER}

_DRUM_DETAIL = [
    (StemKind.KICK, "Kick"),
    (StemKind.SNARE, "Snare"),
    (StemKind.TOMS, "Toms"),
    (StemKind.HIHAT, "Hi-hat"),
    (StemKind.CYMBALS, "Cymbals"),
]
_VOCAL_DETAIL = [
    (StemKind.LEAD_VOCALS, "Lead"),
    (StemKind.BACKING_VOCALS, "Cori"),
]

_QUALITY_ITEMS = [("best", "Massima (default)"), ("balanced", "Bilanciata"), ("fast", "Veloce")]


class StemPicker(QWidget):
    start_requested = Signal(object)  # SeparationJob

    def __init__(self, out_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._out_dir = out_dir
        self._source: Path | None = None
        self._duration: float | None = None
        self._build()
        self._wire()
        self._refresh_estimate()

    # -- costruzione ------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        self._source_label = QLabel("")
        self._source_label.setObjectName("dim")
        layout.addWidget(self._source_label)

        shortcuts = QHBoxLayout()
        self._all_button = QPushButton("Tutto")
        self._vocals_button = QPushButton("Solo voce")
        for button in (self._all_button, self._vocals_button):
            button.setMinimumHeight(44)
            shortcuts.addWidget(button)
        layout.addLayout(shortcuts)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._boxes: dict[StemKind, QCheckBox] = {}
        for index, (kind, label) in enumerate(_BASE_CARDS):
            box = QCheckBox(label)
            box.setChecked(kind in _DEFAULT_CHECKED)
            grid.addWidget(box, index // 4, index % 4)
            self._boxes[kind] = box
        layout.addLayout(grid)

        self._drum_group = StemGroup("Dettaglio batteria", _DRUM_DETAIL)
        layout.addWidget(self._drum_group)
        self._vocal_group = StemGroup("Dettaglio voce", _VOCAL_DETAIL)
        self._dereverb_box = QCheckBox("✨ Togli il riverbero (opzione)")
        self._dereverb_box.setStyleSheet("font-style: italic;")
        self._vocal_group.add_option_widget(self._dereverb_box)
        layout.addWidget(self._vocal_group)

        layout.addStretch(1)
        self._build_bottom(layout)

    def _build_bottom(self, layout: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        self._quality = QComboBox()
        for value, label in _QUALITY_ITEMS:
            self._quality.addItem(label, userData=value)
        self._format = QComboBox()
        self._format.addItem("WAV", userData="wav")
        self._format.addItem("FLAC", userData="flac")
        bottom.addWidget(QLabel("Qualità:"))
        bottom.addWidget(self._quality)
        bottom.addWidget(QLabel("Formato:"))
        bottom.addWidget(self._format)
        bottom.addStretch(1)
        self._estimate = QLabel("")
        self._estimate.setObjectName("estimate")
        bottom.addWidget(self._estimate)
        layout.addLayout(bottom)

        self._start = QPushButton("Separa")
        self._start.setObjectName("primary")
        self._start.setMinimumHeight(48)
        layout.addWidget(self._start)

    def _wire(self) -> None:
        self._all_button.clicked.connect(self._select_all)
        self._vocals_button.clicked.connect(self._select_vocals_only)
        for box in self._boxes.values():
            box.toggled.connect(self._refresh_estimate)
        self._drum_group.changed.connect(self._on_detail_changed)
        self._vocal_group.changed.connect(self._on_detail_changed)
        self._dereverb_box.toggled.connect(self._refresh_estimate)
        self._quality.currentIndexChanged.connect(self._refresh_estimate)
        self._start.clicked.connect(self._emit_start)

    # -- interazione ------------------------------------------------------

    def set_source(self, source: Path, duration: float | None) -> None:
        self._source = source
        self._duration = duration
        self._source_label.setText(source.name)
        self._refresh_estimate()

    def set_source_error(self, message: str) -> None:
        """Errore del job precedente, mostrato senza perdere le scelte (§10.1)."""
        name = self._source.name if self._source is not None else ""
        self._source_label.setText(f"{name} — {message}")

    def _select_all(self) -> None:
        # la resa completa: tutti i base, preset resta `best`
        for kind, box in self._boxes.items():
            box.setChecked(kind != StemKind.INSTRUMENTAL)
        self._refresh_estimate()

    def _select_vocals_only(self) -> None:
        # il lavoro veloce: solo voce, preset `balanced` (§8.2)
        for kind, box in self._boxes.items():
            box.setChecked(kind == StemKind.VOCALS)
        self._drum_group.clear()
        self._vocal_group.clear()
        index = next(
            i for i in range(self._quality.count())
            if self._quality.itemData(i) == "balanced"
        )
        self._quality.setCurrentIndex(index)
        self._refresh_estimate()

    def _on_detail_changed(self) -> None:
        # spuntare un derivato seleziona la dipendenza (§5.3, §8.2)
        if self._drum_group.checked_kinds():
            self._boxes[StemKind.DRUMS].setChecked(True)
        if self._vocal_group.checked_kinds():
            self._boxes[StemKind.VOCALS].setChecked(True)
        self._refresh_estimate()

    def _wanted(self) -> tuple[StemKind, ...]:
        wanted = [kind for kind, box in self._boxes.items() if box.isChecked()]
        wanted += self._drum_group.checked_kinds()
        wanted += self._vocal_group.checked_kinds()
        return tuple(wanted)

    def _current_job(self) -> SeparationJob | None:
        wanted = self._wanted()
        if not wanted or self._source is None:
            return None
        return SeparationJob(
            source=self._source,
            wanted=wanted,
            quality=self._quality.currentData(),
            out_dir=self._out_dir,
            fmt=self._format.currentData(),
            device="auto",
            dereverb_vocals=self._dereverb_box.isChecked(),
        )

    def _refresh_estimate(self) -> None:
        job = self._current_job()
        self._start.setEnabled(job is not None)
        if job is None:
            self._estimate.setText("Scegli almeno uno strumento")
            return
        duration = self._duration if self._duration is not None else 240.0
        summary = planning.summarize(job, duration)
        passate = "passata" if summary.n_passes == 1 else "passate"
        eta = planning.format_eta(summary.seconds)
        self._estimate.setText(f"{eta} · {summary.n_passes} {passate}")

    def _emit_start(self) -> None:
        job = self._current_job()
        if job is not None:
            self.start_requested.emit(job)
