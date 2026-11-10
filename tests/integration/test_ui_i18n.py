"""Lingue dell'interfaccia (BUILD_SPEC §8.6): italiano completo, inglese
coerente, scelta persistente, lingua passata al worker."""

from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from test_ui_support import (  # noqa: F401  (fixture)
    all_derived,
    isolated_settings,
    language,
    make_window,
    qapp,
    visit_screens,
    widget_texts,
)

from PySide6.QtCore import QLocale, QSettings, QTranslator

from stemforge.ui import i18n

UI_DIR = Path(i18n.__file__).parent
TS_FILE = i18n.i18n_dir() / "stemforge_it.ts"
QM_FILE = i18n.i18n_dir() / "stemforge_it.qm"
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
_MIN_FRAGMENT = 5  # frammenti più corti ("or", "Bass") darebbero falsi allarmi


def ts_messages(path: Path = TS_FILE) -> list[tuple[str, str, str, str]]:
    """(contesto, sorgente, traduzione, tipo) per ogni messaggio del .ts."""
    root = ET.parse(path).getroot()
    found = []
    for context in root.iter("context"):
        name = context.findtext("name")
        for message in context.iter("message"):
            translation = message.find("translation")
            found.append((
                name, message.findtext("source"), translation.text or "",
                translation.get("type", ""),
            ))
    return found


def fragments(text: str) -> set[str]:
    return {f.strip() for f in _PLACEHOLDER.split(text) if len(f.strip()) >= _MIN_FRAGMENT}


def test_every_message_is_translated_in_italian():
    messages = ts_messages()
    assert len(messages) > 50
    for context, source, translation, kind in messages:
        assert kind == "", f"{context}: {source!r} è {kind}"
        assert translation.strip(), f"{context}: {source!r} senza traduzione"
        assert set(_PLACEHOLDER.findall(source)) == set(_PLACEHOLDER.findall(translation)), (
            f"{context}: segnaposti diversi in {source!r} / {translation!r}"
        )


def test_committed_qm_contains_every_translation(qapp):
    translator = QTranslator()
    assert translator.load(str(QM_FILE)), f"{QM_FILE} illeggibile"
    for context, source, translation, _kind in ts_messages():
        assert translator.translate(context, source) == translation, (context, source)


def _lupdate() -> Path | None:
    name = "pyside6-lupdate.exe" if sys.platform == "win32" else "pyside6-lupdate"
    candidate = Path(sys.executable).parent / name
    return candidate if candidate.exists() else None


def test_ts_is_in_sync_with_the_code(tmp_path: Path):
    """Un testo nuovo nel codice senza traduzione finirebbe in inglese
    davanti a un utente italiano: lupdate su una copia lo scoprirebbe."""
    tool = _lupdate()
    if tool is None:
        pytest.skip("pyside6-lupdate non presente in questo ambiente")
    copy = tmp_path / "check.ts"
    copy.write_bytes(TS_FILE.read_bytes())
    sources = sorted(str(p) for p in UI_DIR.glob("*.py"))
    subprocess.run(
        [str(tool), "-locations", "none", *sources, "-ts", str(copy)],
        check=True, capture_output=True, timeout=120,
    )
    fresh = {(c, s): k for c, s, _t, k in ts_messages(copy)}
    committed = {(c, s) for c, s, _t, _k in ts_messages()}
    assert {key for key, kind in fresh.items() if kind != "vanished"} == committed
    assert "unfinished" not in fresh.values()


@pytest.mark.parametrize("locale, expected", [
    ("it_IT", "it"), ("it_CH", "it"), ("en_US", "en"), ("en_GB", "en"),
    ("de_DE", "en"), ("fr_FR", "en"),
])
def test_language_follows_the_system(locale: str, expected: str):
    assert i18n.system_language(QLocale(locale)) == expected


def test_choice_is_persistent(isolated_settings: Path):
    assert i18n.stored_choice() == ""
    i18n.store_choice("en")
    reread = QSettings(str(isolated_settings), QSettings.Format.IniFormat)
    assert reread.value(i18n.SETTINGS_KEY) == "en"
    assert i18n.preferred_language() == "en"
    i18n.store_choice("xx")  # valore sconosciuto: torna a seguire il sistema
    assert i18n.stored_choice() == ""
    assert i18n.preferred_language() == i18n.system_language()


def test_bundle_translations_live_in_meipass(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert i18n.i18n_dir() == tmp_path / "i18n"


def _leaks(texts: list[str], foreign: set[str]) -> list[str]:
    # parole intere: "Separa" non è un residuo dentro "Separate"
    patterns = {f: re.compile(rf"(?<!\w){re.escape(f)}(?!\w)") for f in foreign}
    return sorted({f for f, p in patterns.items() for t in texts if p.search(t)})


@pytest.mark.parametrize("code", ["it", "en"])
def test_no_half_translated_screen(qapp, language, all_derived, tmp_path, code):
    """Con il sistema in italiano ogni schermata è tutta italiana; in
    inglese nessun residuo italiano (§8.6: mai un italiano a metà)."""
    language(code)
    window = make_window(qapp, tmp_path)
    english, italian = set(), set()
    for _context, source, translation, _kind in ts_messages():
        if source != translation:
            english |= fragments(source) - fragments(translation)
            italian |= fragments(translation) - fragments(source)
    foreign = english if code == "it" else italian
    for screen, widget in visit_screens(window, qapp, tmp_path):
        texts = widget_texts(widget)
        assert texts, screen
        assert _leaks(texts, foreign) == [], f"schermata {screen} ({code})"
    window.close()


def test_footer_switches_language_live_and_remembers(qapp, language, tmp_path):
    language("en")
    window = make_window(qapp, tmp_path)
    combo = window._drop.footer.language
    combo.setCurrentIndex(combo.findData("it"))
    qapp.processEvents()
    assert window._drop.choose_button.text() == "Scegli un file…"
    assert window._picker._start.text() == "Separa"
    assert i18n.stored_choice() == "it"
    assert i18n.active_language() == "it"

    combo.setCurrentIndex(combo.findData("en"))
    qapp.processEvents()
    assert window._drop.choose_button.text() == "Choose a file…"
    assert combo.itemText(0) == "System language"

    combo.setCurrentIndex(0)  # "Lingua del sistema"
    qapp.processEvents()
    assert i18n.stored_choice() == ""
    assert i18n.active_language() == i18n.system_language()
    window.close()


@pytest.mark.parametrize("code", ["it", "en"])
def test_worker_receives_the_ui_language(qapp, language, monkeypatch, code):
    """Contratto con il worker: STEMFORGE_LOCALE nell'ambiente del figlio.
    Il figlio qui è un Python che rimanda indietro la variabile con il
    protocollo vero, così si verifica il percorso intero."""
    from stemforge.ui import bridge as bridge_module

    language(code)
    echo = (
        "import os, sys; from stemforge.worker import protocol; "
        "sys.stdout.write(protocol.encode(protocol.Warning_("
        f"message=os.environ.get({i18n.LOCALE_ENV!r}, 'missing'))) + '\\n')"
    )
    monkeypatch.setattr(bridge_module, "worker_command", lambda: [sys.executable, "-c", echo])
    worker = bridge_module.WorkerBridge()
    received: list[str] = []
    worker.warning.connect(received.append)
    # come start_job, ma senza scrivere un job su stdin
    worker._process = process = worker._spawn(extra_args=[])
    assert process.processEnvironment().value(i18n.LOCALE_ENV) == code
    assert process.waitForFinished(30_000)  # emette readyRead e finished
    qapp.processEvents()
    assert received == [code]
    assert not worker.running
