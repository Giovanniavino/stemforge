"""Blocco a fisarmonica per i dettagli (batteria, voce) — §8.2.

Chiuso di default: chi vuole i quattro stem classici non deve nemmeno
vederlo. Spuntare un derivato seleziona la dipendenza (lo comunica il
segnale, la logica sta in stem_picker). I testi arrivano da fuori,
già tradotti, a ogni cambio di lingua (`retranslate`).
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QToolButton, QVBoxLayout, QWidget

from stemforge.model.stem import StemKind
from stemforge.ui import a11y

translate = QCoreApplication.translate


class StemGroup(QWidget):
    changed = Signal()

    def __init__(self, kinds: list[StemKind], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 0, 0, 0)
        layout.setSpacing(4)

        # la freccia (destra/giù) dice aperto/chiuso con la forma, e lo
        # stato "checked" lo dice allo screen reader
        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)

        self._panel = QWidget()
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(24, 0, 0, 8)
        panel_layout.setSpacing(4)
        self._boxes: dict[StemKind, QCheckBox] = {}
        for kind in kinds:
            box = QCheckBox()
            box.toggled.connect(lambda _checked: self.changed.emit())
            panel_layout.addWidget(box)
            self._boxes[kind] = box
        self._panel.setVisible(False)
        layout.addWidget(self._panel)

    def retranslate(self, title: str, labels: dict[StemKind, str]) -> None:
        self._toggle.setText(title)
        a11y.name(
            self._toggle, title,
            translate("StemGroup", "Shows or hides the detailed options."),
        )
        for kind, box in self._boxes.items():
            box.setText(labels[kind])
            a11y.name(box, labels[kind])

    def _on_toggled(self, open_: bool) -> None:
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )
        self._panel.setVisible(open_)

    def add_option_widget(self, widget: QWidget) -> None:
        """Per la casella `Togli il riverbero`: opzione, non strumento."""
        self._panel.layout().addWidget(widget)

    def set_stems_available(self, available: bool) -> None:
        """Nasconde gli stem di un modello non ancora adottato (§12-M6):
        un'opzione che produce sempre un avviso è peggio della sua assenza."""
        for box in self._boxes.values():
            if not available:
                box.setChecked(False)
            box.setVisible(available)

    def checked_kinds(self) -> list[StemKind]:
        return [kind for kind, box in self._boxes.items() if box.isChecked()]

    def clear(self) -> None:
        for box in self._boxes.values():
            box.setChecked(False)
