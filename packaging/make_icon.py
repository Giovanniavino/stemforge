"""Disegna l'icona dell'app (packaging/icon.png, 1024 px).

Un quadrato arrotondato scuro con cinque "stem" colorati che escono da
un'unica forma d'onda: il brano che si separa nelle sue tracce.
PyInstaller la converte da sé in .icns (macOS) e .ico (Windows) se Pillow
è installato; make_icon serve solo quando si vuole ridisegnarla.

Uso: python packaging/make_icon.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

SIZE = 1024
OUT = Path(__file__).resolve().parent / "icon.png"
STEM_COLORS = ("#ff5c7a", "#ffb547", "#4fd18b", "#4cb3ff", "#a98bff")


def _wave(x: float, phase: float) -> float:
    return (
        math.sin(x * 0.021 + phase) * 0.6
        + math.sin(x * 0.047 + phase * 1.7) * 0.28
        + math.sin(x * 0.009 + phase * 0.6) * 0.12
    )


def main() -> int:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

    _app = QGuiApplication(sys.argv[:1])
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # sfondo: la griglia delle icone macOS lascia ~10% di margine
    margin = SIZE * 0.09
    tile = QRectF(margin, margin, SIZE - 2 * margin, SIZE - 2 * margin)
    background = QLinearGradient(tile.topLeft(), tile.bottomRight())
    background.setColorAt(0.0, QColor("#22262f"))
    background.setColorAt(1.0, QColor("#0d0f14"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(tile, tile.width() * 0.225, tile.width() * 0.225)

    left = tile.left() + tile.width() * 0.12
    split_x = tile.left() + tile.width() * 0.42
    right = tile.right() - tile.width() * 0.12
    center_y = tile.center().y()

    mix_amp = tile.height() * 0.12
    steps = 160

    # il mix: una forma d'onda bianca a sinistra
    mix = QPainterPath()
    mix.moveTo(QPointF(left, center_y + _wave(left, 0.0) * mix_amp))
    for i in range(1, steps + 1):
        x = left + (split_x - left) * i / steps
        mix.lineTo(QPointF(x, center_y + _wave(x, 0.0) * mix_amp))
    round_pen = (Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # gli stem: cinque linee che nascono dalla fine del mix e si aprono a
    # ventaglio, ognuna con la sua onda più calma (disegnate prima del mix,
    # così il punto di separazione resta pulito)
    spread = tile.height() * 0.5
    for index, color in enumerate(STEM_COLORS):
        offset = (index - 2) / 2.0
        path = QPainterPath()
        path.moveTo(QPointF(split_x, center_y + _wave(split_x, 0.0) * mix_amp))
        for i in range(1, steps + 1):
            t = i / steps
            x = split_x + (right - split_x) * t
            ease = t * t * (3 - 2 * t)
            lane = center_y + offset * spread * 0.5 * ease
            amp = mix_amp * (1 - ease) + tile.height() * 0.03 * ease
            path.lineTo(QPointF(x, lane + _wave(x, index * 1.3 * ease) * amp))
        painter.setPen(QPen(QColor(color), SIZE * 0.024, *round_pen))
        painter.drawPath(path)

    painter.setPen(QPen(QColor("#f3f4f7"), SIZE * 0.026, *round_pen))
    painter.drawPath(mix)

    painter.end()
    if not image.save(str(OUT)):
        print(f"impossibile scrivere {OUT}", file=sys.stderr)
        return 1
    print(f"icona scritta: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
