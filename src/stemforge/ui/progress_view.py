"""Schermata 3: avanzamento (§8.3).

La barra è già globale e pesata (la somma pesata la fa il worker,
_Progress in pipeline.py): qui si mostra, non si calcola. Il tempo
rimanente usa una media mobile per non saltellare, e oltre i 10 minuti
mostra anche l'orario previsto di fine.

La fase si annuncia allo screen reader quando cambia (§8.6); il tempo
rimanente no: ogni 2 s sarebbe rumore che copre tutto il resto.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.ui import a11y

translate = QCoreApplication.translate

_SMOOTHING = 0.25  # media mobile esponenziale del tempo rimanente
_LONG_WAIT_S = 600.0
_REFRESH_MS = 2000  # §8.3: tempo rimanente aggiornato ogni 2 s
_BAR_STEPS = 1000
_MIN_PROGRESS_FOR_ETA = 0.005  # sotto, la stima è solo rumore


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
        self._phase.setWordWrap(True)
        layout.addWidget(self._phase)

        self._bar = QProgressBar()
        self._bar.setRange(0, _BAR_STEPS)
        layout.addWidget(self._bar)

        self._remaining = QLabel("")
        self._remaining.setObjectName("dim")
        self._remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._remaining.setWordWrap(True)
        layout.addWidget(self._remaining)

        self._warnings = QLabel("")
        self._warnings.setObjectName("dim")
        self._warnings.setWordWrap(True)
        self._warnings.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._warnings)

        layout.addStretch(1)
        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName("danger")
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh_remaining)

        self._started_at = 0.0
        self._value = 0.0
        self._smoothed_s: float | None = None
        self._phase_is_default = True
        self._retranslate()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def _retranslate(self) -> None:
        self.cancel_button.setText(translate("ProgressView", "Cancel"))
        a11y.name(
            self.cancel_button,
            translate("ProgressView", "Cancel"),
            translate("ProgressView", "Stops the separation and deletes the partial files (Esc)."),
        )
        a11y.name(self._bar, translate("ProgressView", "Separation progress"))
        if self._phase_is_default:
            self._phase.setText(translate("ProgressView", "Preparing…"))

    def reset(self) -> None:
        self._bar.setValue(0)
        self._phase_is_default = True
        self._phase.setText(translate("ProgressView", "Preparing…"))
        self._remaining.setText("")
        self._warnings.setText("")
        self._started_at = time.monotonic()
        self._value = 0.0
        self._smoothed_s = None
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def set_phase(self, label: str, _index: int, _count: int) -> None:
        if label == self._phase.text():
            return
        self._phase_is_default = False
        self._phase.setText(label)
        a11y.announce(self._phase, label)

    def set_progress(self, value: float) -> None:
        self._value = value
        self._bar.setValue(int(value * _BAR_STEPS))

    def add_warning(self, message: str) -> None:
        current = self._warnings.text()
        self._warnings.setText(f"{current}\n{message}".strip())
        a11y.announce(self._warnings, message)

    def _refresh_remaining(self) -> None:
        if self._value <= _MIN_PROGRESS_FOR_ETA:
            return
        elapsed = time.monotonic() - self._started_at
        estimate = elapsed * (1.0 - self._value) / self._value
        if self._smoothed_s is None:
            self._smoothed_s = estimate
        else:
            self._smoothed_s += _SMOOTHING * (estimate - self._smoothed_s)
        text = format_remaining(self._smoothed_s)
        if self._smoothed_s > _LONG_WAIT_S:
            eta = time.strftime("%H:%M", time.localtime(time.time() + self._smoothed_s))
            text = translate("ProgressView", "{remaining} — ready around {time}").format(
                remaining=text, time=eta
            )
        self._remaining.setText(text)


def format_remaining(seconds: float) -> str:
    if seconds < 90:
        return translate("ProgressView", "about {seconds} seconds left").format(
            seconds=max(1, round(seconds))
        )
    minutes = round(seconds / 60)
    if minutes < 90:
        return translate("ProgressView", "about {minutes} minutes left").format(minutes=minutes)
    hours = int(minutes // 60)
    return translate("ProgressView", "about {hours} h {minutes} min left").format(
        hours=hours, minutes=f"{minutes - hours * 60:02d}"
    )
