"""Blocco a fisarmonica per i dettagli (batteria, voce) — §8.2.

Chiuso di default: chi vuole i quattro stem classici non deve nemmeno
vederlo. Spuntare un derivato seleziona la dipendenza (lo comunica il
segnale, la logica sta in stem_picker).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QToolButton, QVBoxLayout, QWidget

from stemforge.model.stem import StemKind


class StemGroup(QWidget):
    changed = Signal()

    def __init__(
        self,
        title: str,
        kinds: list[tuple[StemKind, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 0, 0, 0)
        layout.setSpacing(4)

        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle)

        self._panel = QWidget()
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(24, 0, 0, 8)
        panel_layout.setSpacing(4)
        self._boxes: dict[StemKind, QCheckBox] = {}
        for kind, label in kinds:
            box = QCheckBox(label)
            box.toggled.connect(lambda _checked: self.changed.emit())
            panel_layout.addWidget(box)
            self._boxes[kind] = box
        self._panel.setVisible(False)
        layout.addWidget(self._panel)

    def _on_toggled(self, open_: bool) -> None:
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )
        self._panel.setVisible(open_)

    def add_option_widget(self, widget: QWidget) -> None:
        """Per la casella `Togli il riverbero`: opzione, non strumento."""
        self._panel.layout().addWidget(widget)

    def checked_kinds(self) -> list[StemKind]:
        return [kind for kind, box in self._boxes.items() if box.isChecked()]

    def clear(self) -> None:
        for box in self._boxes.values():
            box.setChecked(False)
