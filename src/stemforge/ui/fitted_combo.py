"""Un QComboBox che non taglia la voce più lunga col testo grande (§8.6).

Con AdjustToContents Qt misura le voci arrotondando i font frazionari
(testo al 200%, Linux e macOS): il campo resta 1 px più stretto del
testo e la voce si tronca. Due pixel di margine bastano.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QComboBox, QWidget

_SLACK_PX = 2


class FittedComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # il default (AdjustToContentsOnFirstShow) misura una volta sola:
        # dopo un cambio di lingua la voce più lunga resterebbe tagliata
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width() + _SLACK_PX, hint.height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width() + _SLACK_PX, hint.height())
