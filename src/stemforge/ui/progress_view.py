"""Schermata 3: avanzamento (§8.3).

La barra è già globale e pesata (la somma pesata la fa il worker,
_Progress in pipeline.py): qui si mostra, non si calcola. Il tempo
rimanente usa una media mobile per non saltellare, e oltre i 10 minuti
mostra anche l'orario previsto di fine.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SMOOTHING = 0.25  # media mobile esponenziale del tempo rimanente
_LONG_WAIT_S = 600.0


class ProgressView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(16)
        layout.addStretch(1)

        self._phase = QLabel("")
        self._phase.setObjectName("title")
        self._phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._phase)

        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        layout.addWidget(self._bar)

        self._remaining = QLabel("")
        self._remaining.setObjectName("dim")
        self._remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._remaining)

        self._warnings = QLabel("")
        self._warnings.setObjectName("dim")
        self._warnings.setWordWrap(True)
        self._warnings.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._warnings)

        layout.addStretch(1)
        self.cancel_button = QPushButton("Annulla")
        self.cancel_button.setObjectName("danger")
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # aggiornamento del tempo rimanente ogni 2 s (§8.3)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_remaining)

        self._started_at = 0.0
        self._value = 0.0
        self._smoothed_s: float | None = None

    def reset(self) -> None:
        self._bar.setValue(0)
        self._phase.setText("Preparo…")
        self._remaining.setText("")
        self._warnings.setText("")
        self._started_at = time.monotonic()
        self._value = 0.0
        self._smoothed_s = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def set_phase(self, label: str, _index: int, _count: int) -> None:
        self._phase.setText(label)

    def set_progress(self, value: float) -> None:
        self._value = value
        self._bar.setValue(int(value * 1000))

    def add_warning(self, message: str) -> None:
        current = self._warnings.text()
        self._warnings.setText(f"{current}\n{message}".strip())

    def _refresh_remaining(self) -> None:
        if self._value <= 0.005:
            return
        elapsed = time.monotonic() - self._started_at
        estimate = elapsed * (1.0 - self._value) / self._value
        if self._smoothed_s is None:
            self._smoothed_s = estimate
        else:
            self._smoothed_s += _SMOOTHING * (estimate - self._smoothed_s)
        text = _format_remaining(self._smoothed_s)
        if self._smoothed_s > _LONG_WAIT_S:
            eta = time.strftime("%H:%M", time.localtime(time.time() + self._smoothed_s))
            text += f" — pronto verso le {eta}"
        self._remaining.setText(text)


def _format_remaining(seconds: float) -> str:
    if seconds < 90:
        return f"circa {max(1, round(seconds))} secondi rimanenti"
    minutes = round(seconds / 60)
    if minutes < 90:
        return f"circa {minutes} minuti rimanenti"
    hours = int(minutes // 60)
    return f"circa {hours} h {minutes - hours * 60:02d} min rimanenti"
