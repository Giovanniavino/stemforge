"""Accessibilità (BUILD_SPEC §8.6): contrasto WCAG AA calcolato sui colori
di theme.py, un nome accessibile per ogni controllo, avanzamento ed esiti
annunciati agli screen reader, nessuna informazione affidata al solo
colore. La tastiera sta in test_ui_keyboard.py."""

from __future__ import annotations

import re
from dataclasses import fields
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
    write_manifest,
)

from PySide6 import QtGui
from PySide6.QtGui import QAccessible, QImage
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QProgressBar,
    QWidget,
)

from stemforge.ui import a11y, theme

# simboli decorativi (frecce, ▶ ■, emoji): nel testo visibile sì, nel nome no
_DECORATIVE = re.compile("[←-⯿✀-➿\U0001f000-\U0001faff]")
_INTERACTIVE = (QAbstractButton, QComboBox, QAbstractItemView, QProgressBar)


# -- contrasto (WCAG 2.1, 1.4.3 e 1.4.11) -----------------------------------


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    r, g, b = (_channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_contrast_formula_matches_wcag_reference_values():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert contrast("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)  # il grigio AA limite


@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=lambda p: p.name)
def test_every_color_pair_meets_aa(palette: theme.Palette):
    failures = []
    for fg, bg, minimum in theme.CONTRAST_PAIRS:
        ratio = contrast(getattr(palette, fg), getattr(palette, bg))
        if ratio < minimum:
            failures.append(f"{fg} su {bg}: {ratio:.2f} < {minimum}")
    assert failures == []


def test_every_color_in_the_stylesheet_is_in_a_checked_pair():
    """Una regola di colore nuova senza la sua coppia sfuggirebbe al test
    di contrasto: ogni colore di testo, bordo o riempimento del foglio di
    stile deve comparire in CONTRAST_PAIRS."""
    sheet = theme._STYLESHEET.template
    used = set(re.findall(r"(?:^|[\s;{])(?:color|selection-color):\s*\$(\w+)", sheet))
    used |= set(re.findall(r"border[\w-]*:[^;]*\$(\w+)", sheet))
    used |= set(re.findall(r"background-color:\s*\$(accent\w*|selection)", sheet))
    checked = {name for pair in theme.CONTRAST_PAIRS for name in pair[:2]}
    palette_fields = {f.name for f in fields(theme.Palette)}
    assert used <= palette_fields
    assert used - checked == set()


def test_checkbox_colors_come_from_checked_pairs():
    for palette in (theme.LIGHT, theme.DARK):
        colors = theme.indicator_colors(palette)
        assert contrast(colors.border, palette.background) >= theme.NON_TEXT_AA
        assert contrast(colors.border, palette.surface) >= theme.NON_TEXT_AA
        assert contrast(colors.mark, colors.accent) >= theme.TEXT_AA
        assert contrast(colors.accent, palette.background) >= theme.NON_TEXT_AA


# -- nomi accessibili --------------------------------------------------------


def _accessible_name(widget: QWidget) -> str:
    iface = QAccessible.queryAccessibleInterface(widget)
    assert iface is not None, widget
    return iface.text(QAccessible.Text.Name)


def test_every_control_has_an_accessible_name(qapp, language, all_derived, tmp_path):
    language("it")
    window = make_window(qapp, tmp_path)
    seen = 0
    for screen, page in visit_screens(window, qapp, tmp_path):
        for widget in page.findChildren(QWidget):
            if not isinstance(widget, _INTERACTIVE) or not widget.isVisibleTo(window):
                continue
            seen += 1
            name = _accessible_name(widget)
            label = f"{screen}: {type(widget).__name__} {widget.objectName()!r}"
            assert name.strip(), f"{label} senza nome accessibile"
            assert not _DECORATIVE.search(name), f"{label}: simbolo nel nome {name!r}"
    assert seen >= 25  # 3 + 16 + 1 + 4 controlli, con le fisarmoniche aperte
    window.close()


def test_buttons_explain_what_they_do(qapp, language, tmp_path):
    language("it")
    window = make_window(qapp, tmp_path)
    for button in (
        window._drop.choose_button, window._drop.footer.diagnostics,
        window._progress.cancel_button, window._result._reveal_button,
        window._result._again, window._picker._start,
    ):
        assert button.accessibleDescription().strip(), button.text()
    window.close()


# -- annunci agli screen reader ---------------------------------------------


@pytest.fixture()
def announcements(monkeypatch):
    """Ogni annuncio come (tipo di evento, testo annunciato)."""
    heard: list[tuple[object, str]] = []

    def capture(event):
        message = getattr(event, "message", None)
        text = message() if callable(message) else event.object().accessibleDescription()
        heard.append((event.type(), text))

    monkeypatch.setattr(a11y, "_send", capture)
    return heard


def _texts(heard) -> list[str]:
    return [text for kind, text in heard if kind != QAccessible.Event.DescriptionChanged]


def test_progress_announces_phase_and_quarters_only(qapp, language, announcements):
    from stemforge.ui.progress_view import ProgressView

    language("it")
    view = ProgressView()
    view.reset()
    view.set_phase("Separazione — passata 1 di 2", 1, 2)
    view.set_phase("Separazione — passata 1 di 2", 1, 2)  # uguale: niente rumore
    for value in (0.1, 0.26, 0.3, 0.55, 0.8, 0.99, 1.0):
        view.set_progress(value)
    view.stop()
    assert _texts(announcements) == [
        "Separazione — passata 1 di 2", "25% completato", "50% completato", "75% completato",
    ]
    if not hasattr(QtGui, "QAccessibleAnnouncementEvent"):
        # Qt < 6.8: l'annuncio è un Alert che NVDA e VoiceOver leggono
        assert {kind for kind, _ in announcements} >= {QAccessible.Event.Alert}


def test_outcomes_are_announced(qapp, language, announcements, tmp_path: Path):
    from stemforge.model.job import SeparationJob
    from stemforge.model.stem import StemKind

    language("it")
    window = make_window(qapp, tmp_path)
    window._drop._accept([tmp_path / "foto.jpg"])
    out = tmp_path / "out" / "brano"
    window._on_done(str(out), str(write_manifest(out)))
    song = tmp_path / "brano.wav"
    song.touch()
    window._on_files([song])
    window._current_job = SeparationJob(
        source=song, wanted=(StemKind.VOCALS,), quality="fast", out_dir=tmp_path,
    )
    window._on_failed("File illeggibile.", "detail")
    window._on_cancelled()
    heard = _texts(announcements)
    assert "Questo non è un file audio che conosco." in heard
    assert "Separazione finita: 3 stem pronti." in heard
    assert "File illeggibile." in heard
    assert "Separazione annullata." in heard
    window.close()


# -- mai il solo colore ------------------------------------------------------


def _gray(widget: QWidget) -> QImage:
    return widget.grab().toImage().convertToFormat(QImage.Format.Format_Grayscale8)


@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=lambda p: p.name)
def test_states_differ_in_shape_or_lightness_not_only_hue(qapp, themed, palette):
    """In scala di grigi (cioè senza tinta) spuntata/vuota e drop attivo/
    inattivo devono restare distinguibili."""
    themed(palette)
    box = QCheckBox("Voce")
    box.resize(120, 32)
    box.setChecked(False)
    unchecked = _gray(box)
    box.setChecked(True)
    assert _gray(box) != unchecked

    from stemforge.ui.drop_zone import DropZone

    zone = DropZone()
    zone.resize(400, 300)
    idle = _gray(zone._frame)
    zone._set_drag_active(True)
    assert _gray(zone._frame) != idle
    sheet = theme.stylesheet(palette, 12)
    assert "border-left: 5px solid" in sheet  # riga selezionata: una barra, non solo un fondo
    assert "2px dashed" in sheet and "3px solid" in sheet  # drop: tratteggio -> linea piena
