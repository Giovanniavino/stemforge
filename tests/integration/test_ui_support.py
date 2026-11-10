"""Attrezzi condivisi dai test dell'interfaccia (qui nessun test).

Porta ogni schermata in uno stato "pieno" (file scelto, fisarmoniche
aperte, avanzamento con stima lunga, risultato con tre stem) perché i
controlli su lingue, nomi accessibili e testi tagliati vedano tutti i
testi che l'utente può vedere, non solo quelli dello stato iniziale.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QLabel,
    QListWidget,
    QWidget,
)

from stemforge.model.job import StemFile  # noqa: E402
from stemforge.model.manifest import (  # noqa: E402
    AudioInfo,
    EngineInfo,
    Manifest,
    SourceInfo,
)
from stemforge.model.stem import StemKind  # noqa: E402

LONG_WAIT_ELAPSED_S = 1200.0  # a metà dopo 20 min: la stima mostra l'orario


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """La scelta della lingua va in un .ini temporaneo, mai nel registro."""
    from stemforge.ui import i18n

    path = tmp_path / "settings.ini"
    monkeypatch.setenv(i18n.SETTINGS_ENV, str(path))
    return path


@pytest.fixture()
def language(qapp, isolated_settings):
    """`language("it")` installa una lingua; alla fine si torna all'inglese."""
    from stemforge.ui import i18n

    def apply(code: str) -> None:
        assert i18n.apply_language(code), f"traduzione {code} non caricata"
        qapp.processEvents()  # LanguageChange arriva ai widget come evento

    yield apply
    i18n.apply_language(i18n.SOURCE_LANGUAGE)
    qapp.processEvents()


@pytest.fixture()
def themed(qapp):
    """`themed(palette, text_scale)`; alla fine niente foglio di stile."""
    from stemforge.ui import theme

    def apply(palette=None, text_scale: float = 1.0):
        chosen = theme.apply_theme(qapp, palette, text_scale)
        qapp.processEvents()
        return chosen

    yield apply
    qapp.setStyleSheet("")


@pytest.fixture()
def all_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mostra anche i dettagli batteria/voce: più testi da controllare."""
    from stemforge.worker import planning

    monkeypatch.setattr(
        planning, "derived_options",
        lambda: planning.DerivedOptions(drum_detail=True, vocal_split=True, dereverb=True),
    )


def write_manifest(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stems = tuple(
        StemFile(kind=kind, file=f"{kind.value}.wav", peak_dbfs=-1.25, rms_dbfs=-18.0)
        for kind in (StemKind.VOCALS, StemKind.DRUMS, StemKind.BASS)
    )
    manifest = Manifest(
        source=SourceInfo(name="brano.wav", sha1="0" * 40, duration_s=201.0),
        audio=AudioInfo(samplerate=44100, channels=2, bit_depth=24),
        engine=EngineInfo(backend="demucs4", model="htdemucs_ft", quality="best",
                          version="test"),
        stems=stems,
        created_utc="2026-11-10T10:00:00Z",
    )
    path = out_dir / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    return path


def make_window(qapp, tmp_path: Path):
    from stemforge.ui.main_window import MainWindow

    window = MainWindow(out_dir=tmp_path / "out")
    window.show()
    window.activateWindow()
    qapp.processEvents()
    return window


def visit_screens(window, qapp, tmp_path: Path) -> Iterator[tuple[str, QWidget]]:
    """Ogni schermata, piena, mentre è quella visibile."""
    window._drop._accept([tmp_path / "note.txt"])  # rifiuto inline
    window._drop.footer._on_exported(str(tmp_path / "diagnostica.zip"))
    window._show_drop()
    qapp.processEvents()
    yield "drop", window._drop

    song = tmp_path / "brano.wav"
    song.touch()
    window._on_files([song])
    for group in (window._picker._drum_group, window._picker._vocal_group):
        group._toggle.setChecked(True)
    qapp.processEvents()
    yield "picker", window._picker

    progress = window._progress
    progress.reset()
    progress.set_phase("1/3", 1, 3)  # le fasi arrivano dal worker già tradotte
    progress._started_at = time.monotonic() - LONG_WAIT_ELAPSED_S
    progress.set_progress(0.5)
    progress._refresh_remaining()
    progress.add_warning("warning")
    progress.stop()
    window._show(progress, progress.cancel_button)
    qapp.processEvents()
    yield "progress", progress

    out = tmp_path / "out" / "brano"
    window._result.show_result(out, write_manifest(out), ["warning"])
    window._show(window._result, window._result.initial_focus())
    qapp.processEvents()
    yield "result", window._result


def widget_texts(widget: QWidget) -> list[str]:
    """Il testo che si vede e quello che legge lo screen reader."""
    texts: list[str] = []
    for child in [widget, *widget.findChildren(QWidget)]:
        if not child.isVisibleTo(widget.window()):
            continue
        if isinstance(child, (QLabel, QAbstractButton)):
            texts.append(child.text())
        if isinstance(child, QComboBox):
            texts += [child.itemText(i) for i in range(child.count())]
        if isinstance(child, QListWidget):
            texts += [child.item(i).text() for i in range(child.count())]
        texts += [child.accessibleName(), child.accessibleDescription(), child.toolTip()]
    return [t for t in texts if t]
