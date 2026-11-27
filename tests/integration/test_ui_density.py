"""Alta densità e testi non tagliati (BUILD_SPEC §8.6).

Pseudo-lingua: ogni testo dell'interfaccia diventa più lungo del 40% e
pieno di accenti ("Separate" -> "Šéþáŕáţéšép"), come farebbe una lingua
lunga. Poi, per ogni schermata piena, si misura con QFontMetrics il
testo di pulsanti, caselle, etichette e menu e lo si confronta con lo
spazio che il widget ha davvero: un testo più largo del suo spazio è un
testo tagliato.

Scala: 1.0 / 1.5 / 2.0 sia come testo di sistema ingrandito (in questo
processo, `apply_theme(text_scale=...)`) sia come scala dello schermo
(QT_SCALE_FACTOR, in un processo a parte perché si fissa all'avvio).
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_ui_support import (  # noqa: F401  (fixture)
    all_derived,
    isolated_settings,
    make_window,
    qapp,
    themed,
    visit_screens,
)

from PySide6.QtCore import QCoreApplication, QRect, Qt, QTranslator
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QToolButton,
    QWidget,
)

from stemforge.ui import theme

SCALES = (1.0, 1.5, 2.0)
EXPANSION = 0.4  # §8.6: pseudo-lingua più lunga del 40%
_PLACEHOLDER = re.compile(r"(\{[a-z_]+\})")
_WORD = re.compile(r"[A-Za-z]+")
_ACCENTS = str.maketrans(
    "aeiouycnsrtzAEIOUYCNSRTZ", "áéíöüÿçñšŕţžÅÉÎÖÛŸÇÑŠŔŢŽ"
)
_MNEMONIC = re.compile(r"&(?!&)")
_UNBOUNDED_PX = 100_000
_SETTLE_ROUNDS = 6


# -- pseudo-lingua -----------------------------------------------------------


def _stretch(word: str) -> str:
    accented = word.translate(_ACCENTS)
    extra = math.ceil(len(word) * EXPANSION)
    return accented + "".join(accented[i % len(accented)].lower() for i in range(extra))


def pseudo(source: str) -> str:
    """Accenti e +40%, segnaposti {x} e mnemonici & intatti."""
    parts = _PLACEHOLDER.split(source)
    out = [p if _PLACEHOLDER.fullmatch(p) else _WORD.sub(lambda m: _stretch(m.group()), p)
           for p in parts]
    return "".join(out)


class PseudoTranslator(QTranslator):
    """Traduce in pseudo-lingua i soli contesti di StemForge."""

    def __init__(self, contexts: set[str], parent=None) -> None:
        super().__init__(parent)
        self._contexts = contexts

    def translate(self, context, source, disambiguation=None, n=-1):  # noqa: N802
        return pseudo(source) if context in self._contexts else ""

    def isEmpty(self) -> bool:  # noqa: N802
        return False


def app_contexts() -> set[str]:
    from test_ui_i18n import ts_messages

    return {context for context, *_rest in ts_messages()}


# -- misure ------------------------------------------------------------------


def _shown(text: str) -> str:
    return _MNEMONIC.sub("", text)


def _button_contents(widget: QAbstractButton, element: QStyle.SubElement) -> QRect:
    option = QStyleOptionButton()
    widget.initStyleOption(option)
    return widget.style().subElementRect(element, option, widget)


def _label_problem(label: QLabel) -> str | None:
    text = _shown(label.text()) if label.buddy() is not None else label.text()
    area = label.contentsRect()
    metrics = label.fontMetrics()
    if label.wordWrap():
        # una parola che non si può spezzare esce dal rettangolo in larghezza;
        # solo l'allineamento orizzontale, come fa QLabel per misurarsi
        horizontal = label.alignment() & Qt.AlignmentFlag.AlignHorizontal_Mask
        flags = int(horizontal) | int(Qt.TextFlag.TextWordWrap)
        needed = metrics.boundingRect(QRect(0, 0, area.width(), _UNBOUNDED_PX), flags, text)
        if needed.width() > area.width() or needed.height() > area.height():
            return f"{needed.width()}x{needed.height()} in {area.width()}x{area.height()}"
        return None
    lines = text.split("\n")
    width = max(metrics.horizontalAdvance(line) for line in lines)
    height = len(lines) * metrics.lineSpacing()
    if width > area.width() or height > area.height() + metrics.leading():
        return f"{width}x{height} in {area.width()}x{area.height()}"
    return None


def _button_problem(button: QAbstractButton) -> str | None:
    if isinstance(button, QToolButton):
        # freccia accanto al testo: lo spazio lo calcola lo stile stesso
        hint, size = button.sizeHint(), button.size()
        ok = size.width() >= hint.width() and size.height() >= hint.height()
        return None if ok else f"{size.width()}x{size.height()} < {hint.width()}x{hint.height()}"
    element = (QStyle.SubElement.SE_CheckBoxContents if isinstance(button, QCheckBox)
               else QStyle.SubElement.SE_PushButtonContents)
    area = _button_contents(button, element)
    metrics = button.fontMetrics()
    width = metrics.horizontalAdvance(_shown(button.text()))
    if width > area.width() or metrics.height() > area.height():
        return f"{width}x{metrics.height()} in {area.width()}x{area.height()}"
    return None


def _combo_problem(combo: QComboBox) -> str | None:
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    field = combo.style().subControlRect(
        QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, combo
    )
    metrics = combo.fontMetrics()
    width = max(metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
    return f"{width} in {field.width()}" if width > field.width() else None


def clipped(page: QWidget) -> list[str]:
    """Ogni testo visibile della schermata più largo del suo spazio."""
    problems = []
    window = page.window()
    for widget in page.findChildren(QWidget):
        if not widget.isVisibleTo(window):
            continue
        problem = None
        if isinstance(widget, QLabel) and widget.text():
            problem = _label_problem(widget)
        elif isinstance(widget, QAbstractButton) and widget.text():
            problem = _button_problem(widget)
        elif isinstance(widget, QComboBox) and widget.count():
            problem = _combo_problem(widget)
        if problem:
            text = widget.text() if hasattr(widget, "text") else type(widget).__name__
            problems.append(f"{type(widget).__name__} {text!r}: {problem}")
    return problems


def settle(app) -> None:
    """I layout annidati si ricalcolano un livello per giro di eventi:
    con l'app in esecuzione succede da sé, qui va dato il tempo."""
    for _ in range(_SETTLE_ROUNDS):
        app.processEvents()


def check_all_screens(app, tmp_path: Path) -> dict[str, list[str]]:
    """Pseudo-lingua installata, tutte le schermate piene, cosa si taglia."""
    translator = PseudoTranslator(app_contexts(), app)
    QCoreApplication.installTranslator(translator)
    app.processEvents()
    try:
        window = make_window(app, tmp_path)
        result = {}
        for screen, page in visit_screens(window, app, tmp_path):
            settle(app)
            result[screen] = clipped(page)
        window.close()
        return result
    finally:
        QCoreApplication.removeTranslator(translator)
        app.processEvents()


# -- test --------------------------------------------------------------------


def test_pseudo_language_is_longer_and_accented():
    source = "Estimated time: {estimate}. Enter starts."
    result = pseudo(source)
    assert len(result) >= len(source) * (1 + EXPANSION) - len("{estimate}")
    assert "{estimate}" in result and "É" in result
    assert pseudo("&Quality:").startswith("&")


def test_measure_catches_a_clipped_button(qapp, themed):
    """Il metro deve vedere un taglio vero: senza questo, gli altri test
    potrebbero passare anche con un metro rotto."""
    themed(theme.LIGHT)
    button = QPushButton("A long enough button text")
    host = QWidget()
    button.setParent(host)
    host.show()
    button.setGeometry(0, 0, button.sizeHint().width(), button.sizeHint().height())
    qapp.processEvents()
    assert clipped(host) == []
    button.setGeometry(0, 0, button.sizeHint().width() // 2, button.sizeHint().height())
    assert len(clipped(host)) == 1
    host.close()


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=lambda p: p.name)
def test_no_text_clipped_with_large_text(
    qapp, themed, isolated_settings, all_derived, tmp_path, scale, palette
):
    themed(palette, text_scale=scale)
    problems = check_all_screens(qapp, tmp_path)
    assert set(problems) == {"drop", "picker", "progress", "result"}
    assert {screen: found for screen, found in problems.items() if found} == {}


_CHILD = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication
app = QApplication([])
from stemforge.ui import theme
import test_ui_density as d
theme.apply_theme(app, theme.LIGHT)
problems = d.check_all_screens(app, Path(sys.argv[2]))
print(json.dumps({"ratio": app.primaryScreen().devicePixelRatio(), "problems": problems}))
"""


@pytest.mark.parametrize("factor", ["1.5", "2"])
def test_no_text_clipped_with_screen_scale(tmp_path, factor):
    """QT_SCALE_FACTOR vale solo all'avvio di Qt: un processo a parte."""
    env = dict(os.environ, QT_SCALE_FACTOR=factor, QT_QPA_PLATFORM="offscreen",
               STEMFORGE_SETTINGS=str(tmp_path / "settings.ini"))
    run = subprocess.run(
        [sys.executable, "-c", _CHILD, str(Path(__file__).parent), str(tmp_path)],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, run.stderr[-3000:]
    report = json.loads(run.stdout.strip().splitlines()[-1])
    assert report["ratio"] == pytest.approx(float(factor))
    assert {screen: found for screen, found in report["problems"].items() if found} == {}


def test_window_grows_instead_of_clipping(qapp, themed, isolated_settings, tmp_path):
    """Con il testo al 200% la finestra si allarga da sé: il minimo del
    layout, non la dimensione predefinita, decide."""
    themed(theme.LIGHT, text_scale=2.0)
    window = make_window(qapp, tmp_path)
    hint = window.minimumSizeHint()
    assert window.width() >= hint.width() and window.height() >= hint.height()
    window.close()
    assert QApplication.instance() is qapp
