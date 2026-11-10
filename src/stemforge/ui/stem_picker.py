"""Schermata 2: scelta strumenti e stima viva del tempo (§8.2).

La schermata dove l'utente decide quanto tempo vuole spendere: la stima
scende visibilmente quando si toglie roba — è il feedback che insegna
che chiedere meno costa meno (§8.2.1).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt, Signal
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
from stemforge.ui import a11y
from stemforge.ui.stem_group import StemGroup
from stemforge.worker import planning

translate = QCoreApplication.translate

# le icone stanno fuori dalle stringhe da tradurre e fuori dai nomi
# accessibili: VoiceOver non deve leggere "microfono Voce"
_BASE_ICONS: dict[StemKind, str] = {
    StemKind.VOCALS: "🎤",
    StemKind.DRUMS: "🥁",
    StemKind.BASS: "🎸",
    StemKind.GUITAR: "🎸",
    StemKind.PIANO: "🎹",
    StemKind.OTHER: "🎼",
    StemKind.INSTRUMENTAL: "🎛",
}
_DEFAULT_CHECKED = {StemKind.VOCALS, StemKind.DRUMS, StemKind.BASS, StemKind.OTHER}
_GRID_COLUMNS = 4
_DRUM_KINDS = [StemKind.KICK, StemKind.SNARE, StemKind.TOMS, StemKind.HIHAT, StemKind.CYMBALS]
_VOCAL_KINDS = [StemKind.LEAD_VOCALS, StemKind.BACKING_VOCALS]
_QUALITIES = ("best", "balanced", "fast")
_FALLBACK_DURATION_S = 240.0  # durata ignota: un brano tipico


def _base_labels() -> dict[StemKind, str]:
    return {
        StemKind.VOCALS: translate("StemPicker", "Vocals"),
        StemKind.DRUMS: translate("StemPicker", "Drums"),
        StemKind.BASS: translate("StemPicker", "Bass"),
        StemKind.GUITAR: translate("StemPicker", "Guitar"),
        StemKind.PIANO: translate("StemPicker", "Piano"),
        StemKind.OTHER: translate("StemPicker", "Other"),
        StemKind.INSTRUMENTAL: translate("StemPicker", "Instrumental"),
    }


def _drum_labels() -> dict[StemKind, str]:
    return {
        StemKind.KICK: translate("StemPicker", "Kick"),
        StemKind.SNARE: translate("StemPicker", "Snare"),
        StemKind.TOMS: translate("StemPicker", "Toms"),
        StemKind.HIHAT: translate("StemPicker", "Hi-hat"),
        StemKind.CYMBALS: translate("StemPicker", "Cymbals"),
    }


def _vocal_labels() -> dict[StemKind, str]:
    return {
        StemKind.LEAD_VOCALS: translate("StemPicker", "Lead vocals"),
        StemKind.BACKING_VOCALS: translate("StemPicker", "Backing vocals"),
    }


def _quality_labels() -> dict[str, str]:
    return {
        "best": translate("StemPicker", "Best (default)"),
        "balanced": translate("StemPicker", "Balanced"),
        "fast": translate("StemPicker", "Fast"),
    }


def _passes_text(count: int) -> str:
    # due forme bastano per italiano e inglese (una / più di una)
    if count == 1:
        return translate("StemPicker", "1 pass")
    return translate("StemPicker", "{count} passes").format(count=count)


class StemPicker(QWidget):
    start_requested = Signal(object)  # SeparationJob
    back_requested = Signal()

    def __init__(self, out_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._out_dir = out_dir
        self._source: Path | None = None
        self._duration: float | None = None
        self._source_error = ""
        self._build()
        self._wire()
        self._retranslate()

    # -- costruzione ------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        top = QHBoxLayout()
        self._back = QPushButton()
        self._back.setObjectName("quiet")
        self._source_label = QLabel("")
        self._source_label.setObjectName("dim")
        self._source_label.setWordWrap(True)
        top.addWidget(self._back)
        top.addWidget(self._source_label, stretch=1)
        layout.addLayout(top)

        shortcuts = QHBoxLayout()
        self._all_button = QPushButton()
        self._vocals_button = QPushButton()
        for button in (self._all_button, self._vocals_button):
            button.setMinimumHeight(44)
            shortcuts.addWidget(button)
        layout.addLayout(shortcuts)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._boxes: dict[StemKind, QCheckBox] = {}
        for index, kind in enumerate(_BASE_ICONS):
            box = QCheckBox()
            box.setChecked(kind in _DEFAULT_CHECKED)
            grid.addWidget(box, index // _GRID_COLUMNS, index % _GRID_COLUMNS)
            self._boxes[kind] = box
        layout.addLayout(grid)

        self._drum_group = StemGroup(_DRUM_KINDS)
        layout.addWidget(self._drum_group)
        self._vocal_group = StemGroup(_VOCAL_KINDS)
        self._dereverb_box = QCheckBox()
        self._dereverb_box.setObjectName("option")
        self._vocal_group.add_option_widget(self._dereverb_box)
        layout.addWidget(self._vocal_group)
        self._apply_derived_availability()

        layout.addStretch(1)
        self._build_bottom(layout)

    def _apply_derived_availability(self) -> None:
        # §12-M6: un derivato senza modello vero non si mostra affatto
        options = planning.derived_options()
        self._drum_group.set_stems_available(options.drum_detail)
        self._drum_group.setVisible(options.drum_detail)
        self._vocal_group.set_stems_available(options.vocal_split)
        self._dereverb_box.setVisible(options.dereverb)
        if not options.dereverb:
            self._dereverb_box.setChecked(False)
        self._vocal_group.setVisible(options.vocal_split or options.dereverb)

    def _build_bottom(self, layout: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        self._quality = QComboBox()
        for value in _QUALITIES:
            self._quality.addItem("", userData=value)
        self._format = QComboBox()
        self._format.addItem("WAV", userData="wav")
        self._format.addItem("FLAC", userData="flac")
        self._quality_label = QLabel()
        self._quality_label.setBuddy(self._quality)
        self._format_label = QLabel()
        self._format_label.setBuddy(self._format)
        bottom.addWidget(self._quality_label)
        bottom.addWidget(self._quality)
        bottom.addWidget(self._format_label)
        bottom.addWidget(self._format)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        # la stima ha una riga sua: con testi lunghi o ingranditi non
        # costringe la finestra ad allargarsi (§8.6)
        self._estimate = QLabel("")
        self._estimate.setObjectName("estimate")
        self._estimate.setWordWrap(True)
        self._estimate.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._estimate)

        self._start = QPushButton()
        self._start.setObjectName("primary")
        self._start.setMinimumHeight(48)
        layout.addWidget(self._start)

    def _wire(self) -> None:
        self._back.clicked.connect(self.back_requested.emit)
        self._all_button.clicked.connect(self._select_all)
        self._vocals_button.clicked.connect(self._select_vocals_only)
        for box in self._boxes.values():
            box.toggled.connect(self._refresh_estimate)
        self._drum_group.changed.connect(self._on_detail_changed)
        self._vocal_group.changed.connect(self._on_detail_changed)
        self._dereverb_box.toggled.connect(self._refresh_estimate)
        self._quality.currentIndexChanged.connect(self._refresh_estimate)
        self._start.clicked.connect(self.request_start)

    # -- lingua -----------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def _retranslate(self) -> None:
        self._back.setText("← " + translate("StemPicker", "Back"))
        a11y.name(self._back, translate("StemPicker", "Back"),
                  translate("StemPicker", "Back to choosing a song (Esc)."))
        self._all_button.setText(translate("StemPicker", "Everything"))
        a11y.name(self._all_button, translate("StemPicker", "Everything"),
                  translate("StemPicker", "Selects every instrument: the complete result."))
        self._vocals_button.setText(translate("StemPicker", "Vocals only"))
        a11y.name(self._vocals_button, translate("StemPicker", "Vocals only"),
                  translate("StemPicker", "Only the vocals, with the balanced quality: the quick job."))
        for kind, label in _base_labels().items():
            self._boxes[kind].setText(f"{_BASE_ICONS[kind]}  {label}")
            a11y.name(self._boxes[kind], label)
        self._drum_group.retranslate(translate("StemPicker", "Drum detail"), _drum_labels())
        self._vocal_group.retranslate(translate("StemPicker", "Vocal detail"), _vocal_labels())
        dereverb = translate("StemPicker", "Remove the reverb")
        self._dereverb_box.setText("✨ " + translate("StemPicker", "{option} (option)").format(option=dereverb))
        a11y.name(self._dereverb_box, dereverb,
                  translate("StemPicker", "An option applied to the vocals, not an extra instrument."))
        self._retranslate_bottom()
        self._show_source()
        self._refresh_estimate()

    def _retranslate_bottom(self) -> None:
        for index, label in enumerate(_quality_labels()[q] for q in _QUALITIES):
            self._quality.setItemText(index, label)
        self._quality_label.setText(translate("StemPicker", "&Quality:"))
        a11y.name(self._quality, translate("StemPicker", "Quality"),
                  translate("StemPicker", "Higher quality takes longer."))
        self._format_label.setText(translate("StemPicker", "&Format:"))
        a11y.name(self._format, translate("StemPicker", "File format"))
        self._start.setText(translate("StemPicker", "Separate"))

    # -- interazione ------------------------------------------------------

    def set_source(self, source: Path, duration: float | None) -> None:
        self._source = source
        self._duration = duration
        self._source_error = ""
        self._show_source()
        self._refresh_estimate()

    def set_source_error(self, message: str) -> None:
        """Errore del job precedente, mostrato senza perdere le scelte (§10.1)."""
        self._source_error = message
        self._show_source()
        a11y.announce(self._source_label, message)

    def _show_source(self) -> None:
        name = self._source.name if self._source is not None else ""
        if self._source_error:
            name = f"{name} — {self._source_error}"
        self._source_label.setText(name)

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
        self._quality.setCurrentIndex(self._quality.findData("balanced"))
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
            text = translate("StemPicker", "Choose at least one instrument")
            description = text
        else:
            duration = self._duration if self._duration is not None else _FALLBACK_DURATION_S
            summary = planning.summarize(job, duration)
            text = f"{planning.format_eta(summary.seconds)} · {_passes_text(summary.n_passes)}"
            description = translate(
                "StemPicker", "Estimated time: {estimate}. Enter starts."
            ).format(estimate=text)
        self._estimate.setText(text)
        # chi arriva sul pulsante con lo screen reader sente anche la stima
        a11y.name(self._start, translate("StemPicker", "Separate"), description)

    def request_start(self) -> None:
        """Pulsante Separa e tasto Invio (§8.6)."""
        job = self._current_job()
        if job is not None:
            self.start_requested.emit(job)

    def initial_focus(self) -> QWidget:
        return self._start if self._start.isEnabled() else self._all_button
