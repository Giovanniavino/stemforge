"""Tastiera (BUILD_SPEC §8.6): ogni schermata si usa senza mouse, con un
ordine di tabulazione che segue la lettura, Invio = Separa, Esc =
Annulla/Indietro, Cmd/Ctrl+O = scegli file e un focus sempre visibile.

I tasti si mandano con QTest come eventi veri: passano dalla mappa delle
scorciatoie di Qt come quelli premuti da una persona.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from test_ui_support import (  # noqa: F401  (fixture)
    all_derived,
    isolated_settings,
    language,
    make_window,
    qapp,
    themed,
    visit_screens,
)

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from stemforge.ui import conventions, drop_zone, theme

_MAX_CHAIN = 60  # più controlli di così vuol dire un giro di Tab senza fine


@pytest.fixture()
def window(qapp, language, isolated_settings, tmp_path: Path, monkeypatch):
    """Finestra attiva (il focus esiste solo in una finestra attiva) con
    il worker sostituito: nessun processo figlio parte davvero."""
    language("it")
    win = make_window(qapp, tmp_path)
    assert QTest.qWaitForWindowActive(win)
    started: list[object] = []
    cancelled: list[bool] = []
    monkeypatch.setattr(win._bridge, "start_job", started.append)
    monkeypatch.setattr(win._bridge, "cancel", lambda: cancelled.append(True))
    win.started_jobs, win.cancel_calls = started, cancelled
    yield win
    win.close()


def _press(key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    target = QApplication.focusWidget() or QApplication.activeWindow()
    QTest.keyClick(target, key, modifiers)
    QApplication.processEvents()


def _song(tmp_path: Path) -> Path:
    song = tmp_path / "brano.wav"
    song.touch()
    return song


def _to_picker(win, tmp_path: Path) -> None:
    win._on_files([_song(tmp_path)])
    QApplication.processEvents()


# -- ordine di tabulazione ---------------------------------------------------


def _tab_chain(start: QWidget) -> list[QWidget]:
    start.setFocus(Qt.FocusReason.TabFocusReason)
    QApplication.processEvents()
    chain = [QApplication.focusWidget()]
    for _ in range(_MAX_CHAIN):
        _press(Qt.Key.Key_Tab)
        if QApplication.focusWidget() is chain[0]:
            return chain
        chain.append(QApplication.focusWidget())
    raise AssertionError("il Tab non torna al punto di partenza")


def _window_rect(widget: QWidget) -> QRect:
    return QRect(widget.mapTo(widget.window(), QPoint(0, 0)), widget.size())


def reading_order(widgets: list[QWidget]) -> list[QWidget]:
    """Righe dall'alto in basso (due controlli sono sulla stessa riga se
    il centro dell'uno cade nell'altezza dell'altro), in riga da sinistra."""
    rows: list[list[QWidget]] = []
    for widget in sorted(widgets, key=lambda w: _window_rect(w).center().y()):
        center = _window_rect(widget).center().y()
        row = rows[-1] if rows else None
        if row and _window_rect(row[0]).top() <= center <= _window_rect(row[0]).bottom():
            row.append(widget)
        else:
            rows.append([widget])
    return [w for row in rows for w in sorted(row, key=lambda w: _window_rect(w).left())]


def _tab_focusable(page: QWidget) -> list[QWidget]:
    return [
        w for w in page.findChildren(QWidget)
        if w.isVisibleTo(page.window()) and w.isEnabled()
        and w.focusPolicy() & Qt.FocusPolicy.TabFocus
        and w.focusProxy() is None
    ]


def test_tab_visits_every_control_in_reading_order(all_derived, window, qapp, tmp_path):
    seen: dict[str, int] = {}
    for screen, page in visit_screens(window, qapp, tmp_path):
        expected = reading_order(_tab_focusable(page))
        chain = _tab_chain(expected[0])
        names = [w.accessibleName() or type(w).__name__ for w in chain]
        assert chain == expected, f"{screen}: {names}"
        seen[screen] = len(chain)
    # drop: file, lingua, diagnostica; scelta: 21 con le fisarmoniche aperte
    assert seen == {"drop": 3, "picker": 21, "progress": 1, "result": 4}


def test_each_screen_starts_where_the_next_step_is(window, tmp_path):
    window._show_drop()
    assert QApplication.focusWidget() is window._drop.choose_button
    _to_picker(window, tmp_path)
    assert QApplication.focusWidget() is window._picker._start


# -- Invio = Separa ----------------------------------------------------------


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_separates_from_a_checkbox_or_a_menu(window, tmp_path, key):
    _to_picker(window, tmp_path)
    window._picker._boxes[next(iter(window._picker._boxes))].setFocus()
    _press(key)
    assert len(window.started_jobs) == 1
    window._show_picker()
    window._picker._quality.setFocus()
    _press(key)
    assert len(window.started_jobs) == 2
    assert window._stack.currentWidget() is window._progress


def test_enter_on_a_button_presses_that_button(window, tmp_path):
    _to_picker(window, tmp_path)
    picker = window._picker
    picker._vocals_button.setFocus()
    _press(Qt.Key.Key_Return)
    assert window.started_jobs == []  # ha premuto "Solo voce", non Separa
    assert picker._wanted() == (next(iter(picker._boxes)),)
    assert picker._quality.currentData() == "balanced"


def test_enter_does_nothing_when_nothing_is_chosen(window, tmp_path):
    _to_picker(window, tmp_path)
    for box in window._picker._boxes.values():
        box.setChecked(False)
    window._picker._boxes[next(iter(window._picker._boxes))].setFocus()
    _press(Qt.Key.Key_Return)
    assert window.started_jobs == []


# -- Esc = Annulla/Indietro --------------------------------------------------


def test_escape_goes_back_from_choice_and_result(window, tmp_path):
    _to_picker(window, tmp_path)
    _press(Qt.Key.Key_Escape)
    assert window._stack.currentWidget() is window._drop
    assert QApplication.focusWidget() is window._drop.choose_button

    from test_ui_support import write_manifest

    out = tmp_path / "out" / "brano"
    window._on_done(str(out), str(write_manifest(out)))
    assert window._stack.currentWidget() is window._result
    _press(Qt.Key.Key_Escape)
    assert window._stack.currentWidget() is window._drop


def test_escape_cancels_a_running_separation(window, tmp_path):
    _to_picker(window, tmp_path)
    _press(Qt.Key.Key_Return)
    assert window._stack.currentWidget() is window._progress
    assert QApplication.focusWidget() is window._progress.cancel_button
    _press(Qt.Key.Key_Escape)
    assert window.cancel_calls == [True]


def test_escape_does_not_stop_the_first_start(window):
    """Il download dei modelli non ha Annulla (§9.4): Esc non lo tocca."""
    window._preparing = True
    window._stack.setCurrentWidget(window._progress)
    window._progress.setFocus()
    _press(Qt.Key.Key_Escape)
    assert window.cancel_calls == []
    window._preparing = False


# -- Cmd/Ctrl+O = scegli file ------------------------------------------------


@pytest.fixture()
def chooser(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_dialog(parent, title, folder, filters):
        calls.append(title)
        return [str(_song(tmp_path))], filters

    monkeypatch.setattr(drop_zone.QFileDialog, "getOpenFileNames", staticmethod(fake_dialog))
    return calls


def test_open_shortcut_chooses_a_file_from_any_screen(window, chooser, tmp_path):
    window._show_drop()
    # StandardKey.Open: Qt lo traduce in Cmd+O su macOS e Ctrl+O altrove
    _press(Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    assert chooser == ["Scegli un brano"]
    assert window._stack.currentWidget() is window._picker

    from test_ui_support import write_manifest

    out = tmp_path / "out" / "brano"
    window._on_done(str(out), str(write_manifest(out)))
    _press(Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    assert len(chooser) == 2
    assert window._stack.currentWidget() is window._picker


def test_open_shortcut_waits_during_a_job(window, chooser, tmp_path, monkeypatch):
    _to_picker(window, tmp_path)
    _press(Qt.Key.Key_Return)
    monkeypatch.setattr(type(window._bridge), "running", property(lambda _self: True))
    _press(Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    assert chooser == []


def test_shortcut_is_written_the_way_the_system_writes_it():
    text = conventions.shortcut_text(QKeySequence.StandardKey.Open)
    if sys.platform == "darwin":
        assert text == "⌘O"
    else:
        assert text == "Ctrl+O"


@pytest.mark.skipif(sys.platform == "darwin", reason="macOS non usa i mnemonici Alt")
def test_labels_have_mnemonics_to_their_control(window, tmp_path):
    _to_picker(window, tmp_path)
    _press(Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier)  # "&Qualità:"
    assert QApplication.focusWidget() is window._picker._quality
    _press(Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier)  # "&Formato:"
    assert QApplication.focusWidget() is window._picker._format


# -- focus sempre visibile ---------------------------------------------------


def _image(widget: QWidget) -> QImage:
    return widget.grab().toImage()


@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=lambda p: p.name)
def test_focus_is_always_visible(all_derived, window, qapp, themed, tmp_path, palette):
    """Ogni controllo raggiungibile col Tab si disegna diverso quando ha il
    focus: chi usa la tastiera vede sempre dov'è."""
    themed(palette)
    checked = 0
    for screen, page in visit_screens(window, qapp, tmp_path):
        controls = _tab_focusable(page)
        for control in controls:
            other = next(c for c in controls if c is not control) if len(controls) > 1 else None
            if other is not None:
                other.setFocus(Qt.FocusReason.TabFocusReason)
            else:
                window.setFocus()
            qapp.processEvents()
            idle = _image(control)
            control.setFocus(Qt.FocusReason.TabFocusReason)
            qapp.processEvents()
            assert control.hasFocus(), f"{screen}: {control.accessibleName()}"
            assert _image(control) != idle, f"{screen}: focus invisibile su {control.accessibleName()!r}"
            checked += 1
    assert checked == 29
