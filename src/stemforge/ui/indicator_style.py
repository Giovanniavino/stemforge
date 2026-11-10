"""La casella di spunta disegnata con i colori del tema (§8.6).

Lo stile nativo di Windows disegna la casella vuota con i suoi grigi,
che sul tema scuro spariscono (contorno sotto 3:1, WCAG 1.4.11). Qui la
casella usa colori verificati dal test di contrasto: contorno `border`
sullo sfondo, e da spuntata il segno `on_accent` sull'`accent`. Spuntata
e vuota differiscono per la forma (il segno), non solo per il colore.
Tutto il resto lo disegna lo stile nativo.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleOption, QWidget

_BORDER_PX = 2.0
_RADIUS_PX = 3.0
_MARK_PX = 2.2
# il segno di spunta, in frazioni del lato della casella
_MARK_POINTS = ((0.22, 0.52), (0.42, 0.72), (0.78, 0.30))
_DASH_Y = 0.5


@dataclass(frozen=True)
class IndicatorColors:
    border: str  # contorno della casella vuota
    fill: str  # interno della casella vuota
    accent: str  # interno e contorno della casella spuntata
    mark: str  # il segno sopra l'accento
    disabled: str  # contorno e segno di una casella disattivata


class IndicatorStyle(QProxyStyle):
    def __init__(self, colors: IndicatorColors) -> None:
        super().__init__()
        self._colors = colors

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_checkbox(self, option: QStyleOption, painter: QPainter) -> None:
        state = option.state
        checked = bool(state & QStyle.StateFlag.State_On)
        partial = bool(state & QStyle.StateFlag.State_NoChange)
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        c = self._colors
        edge = c.accent if (checked or partial) and enabled else c.border
        if not enabled:
            edge = c.disabled
        fill = c.accent if (checked or partial) and enabled else c.fill
        inset = _BORDER_PX / 2
        box = QRectF(option.rect).adjusted(inset, inset, -inset, -inset)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(edge), _BORDER_PX))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(box, _RADIUS_PX, _RADIUS_PX)
        mark_color = c.mark if enabled else c.disabled
        pen = QPen(QColor(mark_color), _MARK_PX)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if checked:
            painter.drawPolyline(QPolygonF([_at(box, x, y) for x, y in _MARK_POINTS]))
        elif partial:
            painter.drawLine(_at(box, 0.25, _DASH_Y), _at(box, 0.75, _DASH_Y))
        painter.restore()


def _at(box: QRectF, fx: float, fy: float) -> QPointF:
    return QPointF(box.left() + fx * box.width(), box.top() + fy * box.height())
