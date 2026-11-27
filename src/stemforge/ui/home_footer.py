"""Piede della schermata iniziale: lingua e diagnostica (§8.6, §9.9).

Due controlli discreti, nessun menu di preferenze (§8): la lingua si
sceglie qui e resta (QSettings), la diagnostica si esporta qui.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stemforge.ui import a11y, i18n
from stemforge.ui.diagnostics_action import DiagnosticsExporter

translate = QCoreApplication.translate

# i nomi delle lingue si scrivono nella lingua stessa: chi non capisce
# l'interfaccia deve riconoscere la propria
_LANGUAGE_NAMES = (("it", "Italiano"), ("en", "English"))


class HomeFooter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.exporter = DiagnosticsExporter(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self._language_label = QLabel()
        self.language = QComboBox()
        self.language.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._language_label.setBuddy(self.language)
        self.language.addItem("", userData="")
        for code, label in _LANGUAGE_NAMES:
            self.language.addItem(label, userData=code)
        self._select_stored_language()
        self.diagnostics = QPushButton()
        self.diagnostics.setObjectName("quiet")
        row.addWidget(self._language_label)
        row.addWidget(self.language)
        row.addStretch(1)
        row.addWidget(self.diagnostics)
        layout.addLayout(row)

        self.status = QLabel("")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

        self.language.currentIndexChanged.connect(self._on_language)
        self.diagnostics.clicked.connect(lambda: self.exporter.export(self))
        self.exporter.busy.connect(self._on_busy)
        self.exporter.succeeded.connect(self._on_exported)
        self.exporter.failed.connect(self._show_status)
        self.setTabOrder(self.language, self.diagnostics)
        self._retranslate()

    def _select_stored_language(self) -> None:
        index = self.language.findData(i18n.stored_choice())
        self.language.setCurrentIndex(max(index, 0))

    def _on_language(self, _index: int) -> None:
        choice = self.language.currentData() or ""
        i18n.store_choice(choice)
        i18n.apply_language(choice or i18n.system_language())

    def _on_busy(self) -> None:
        self.diagnostics.setEnabled(False)
        self._set_status(translate("HomeFooter", "Exporting the diagnostics…"))

    def _on_exported(self, path: str) -> None:
        self._show_status(translate("HomeFooter", "Diagnostics saved: {path}").format(path=path))

    def _show_status(self, message: str) -> None:
        """Esito finale (riuscita o errore): il pulsante torna usabile."""
        self.diagnostics.setEnabled(True)
        self._set_status(message)

    def _set_status(self, message: str) -> None:
        self.status.setText(message)
        a11y.announce(self.status, message)

    # -- lingua -----------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def _retranslate(self) -> None:
        self._language_label.setText(translate("HomeFooter", "&Language:"))
        self.language.setItemText(0, translate("HomeFooter", "System language"))
        a11y.name(
            self.language,
            translate("HomeFooter", "Interface language"),
            translate("HomeFooter", "The choice is remembered for the next launches."),
        )
        self.diagnostics.setText(translate("HomeFooter", "Export diagnostics…"))
        a11y.name(
            self.diagnostics,
            translate("HomeFooter", "Export diagnostics"),
            translate("HomeFooter", "Saves a zip with the log and the system details in a folder you choose. Nothing is sent."),
        )
