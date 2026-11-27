"""Lingue dell'interfaccia: italiano e inglese (BUILD_SPEC §8.6).

Lingua sorgente nel codice: INGLESE, con l'italiano come traduzione
completa in `resources/i18n/stemforge_it.ts/.qm`. Il perché:
- è lo standard Qt: lupdate, Linguist, le traduzioni di Qt stesso
  (qtbase_it.qm per i dialoghi di sistema) e chiunque arrivi dopo si
  aspettano l'inglese come chiave;
- se il .qm mancasse da un pacchetto rotto, l'interfaccia resta
  coerente in inglese invece di diventare un misto (§8.6: "mai un
  italiano a metà");
- l'utente attuale è italiano: con il sistema in italiano la lingua
  scelta è `it`, e un test verifica che ogni testo abbia la sua
  traduzione italiana e che il .qm committato la contenga.

Aggiornare le traduzioni (dalla radice del repo, ambiente MODERNO):
    pyside6-lupdate -locations none src/stemforge/ui/*.py
        -ts resources/i18n/stemforge_it.ts
    (tradurre in Qt Linguist, poi)
    pyside6-lrelease resources/i18n/stemforge_it.ts
        -qm resources/i18n/stemforge_it.qm
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QLibraryInfo,
    QLocale,
    QSettings,
    QTranslator,
)

SOURCE_LANGUAGE = "en"
LANGUAGES = ("it", "en")
LOCALE_ENV = "STEMFORGE_LOCALE"  # contratto col worker (area E): "it" / "en"
SETTINGS_ENV = "STEMFORGE_SETTINGS"  # file .ini al posto del registro (test)
SETTINGS_KEY = "ui/language"  # "" = segui il sistema

_APP_TRANSLATOR = "stemforge-translator"
_QT_TRANSLATOR = "stemforge-qt-translator"
_ACTIVE_PROPERTY = "stemforgeLanguage"


def i18n_dir() -> Path:
    """Dove stanno i .qm: nel bundle `sys._MEIPASS/i18n`, in sviluppo
    `resources/i18n` alla radice del repo."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        return Path(bundle) / "i18n"
    return Path(__file__).resolve().parents[3] / "resources" / "i18n"


def settings() -> QSettings:
    path = os.environ.get(SETTINGS_ENV)
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("StemForge", "StemForge")


def system_language(locale: QLocale | None = None) -> str:
    """La prima lingua supportata fra quelle preferite dal sistema;
    inglese se nessuna lo è (un tedesco legge meglio l'inglese)."""
    current = locale if locale is not None else QLocale.system()
    for tag in current.uiLanguages():
        code = tag.replace("_", "-").split("-")[0].lower()
        if code in LANGUAGES:
            return code
    return SOURCE_LANGUAGE


def stored_choice() -> str:
    value = settings().value(SETTINGS_KEY, "")
    return value if isinstance(value, str) and value in LANGUAGES else ""


def store_choice(choice: str) -> None:
    """`""` torna a seguire il sistema; la scelta sopravvive al riavvio."""
    store = settings()
    store.setValue(SETTINGS_KEY, choice if choice in LANGUAGES else "")
    store.sync()


def preferred_language() -> str:
    return stored_choice() or system_language()


def active_language() -> str:
    """La lingua in uso adesso (quella da passare al worker)."""
    app = QCoreApplication.instance()
    if app is not None:
        value = app.property(_ACTIVE_PROPERTY)
        if isinstance(value, str) and value in LANGUAGES:
            return value
    return preferred_language()


def apply_language(language: str) -> bool:
    """Installa le traduzioni di `language` e lo rende attivo.

    Installare/rimuovere un traduttore manda LanguageChange a ogni
    widget, che si ritraduce da sé: il cambio vale subito, senza
    riavvio. Ritorna False se il .qm dell'app non si è caricato.
    """
    app = QCoreApplication.instance()
    assert app is not None, "serve una QApplication"
    language = language if language in LANGUAGES else SOURCE_LANGUAGE
    _remove_translator(app, _APP_TRANSLATOR)
    _remove_translator(app, _QT_TRANSLATOR)
    app.setProperty(_ACTIVE_PROPERTY, language)
    if language == SOURCE_LANGUAGE:
        return True
    qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    # qtbase_it: i pulsanti dei dialoghi di Qt e i nomi dei tasti
    _install(app, _QT_TRANSLATOR, f"qtbase_{language}", qt_dir)
    return _install(app, _APP_TRANSLATOR, f"stemforge_{language}", str(i18n_dir()))


def _install(app: QCoreApplication, name: str, file: str, directory: str) -> bool:
    translator = QTranslator(app)
    translator.setObjectName(name)
    if not translator.load(file, directory):
        translator.deleteLater()
        return False
    QCoreApplication.installTranslator(translator)
    return True


def _remove_translator(app: QCoreApplication, name: str) -> None:
    for translator in app.findChildren(QTranslator, name):
        QCoreApplication.removeTranslator(translator)
        translator.setParent(None)
        translator.deleteLater()
