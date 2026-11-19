"""Tema chiaro/scuro dal sistema (BUILD_SPEC §8.6), anche su Qt 6.4.

QStyleHints.colorScheme esiste da Qt 6.5: sul profilo legacy-intel
(PySide6 6.4) il tema si ricava dal registro di Windows e dalla palette
di sistema letta prima che l'app la sostituisca con la sua. Questi test
girano con entrambe le versioni e provano il ramo che ciascuna usa.
"""

from __future__ import annotations

import sys

import pytest
from test_ui_support import qapp, themed  # noqa: F401  (fixture)

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from stemforge.ui import theme

_HAS_COLOR_SCHEME = hasattr(Qt, "ColorScheme")


def _palette(window: str) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(window))
    return palette


def test_palette_lightness_tells_dark_from_light():
    assert theme.palette_is_dark(_palette("#202020"))
    assert not theme.palette_is_dark(_palette("#ececec"))


def test_style_hints_only_where_qt_knows(qapp):
    verdict = theme.style_hints_dark(qapp)
    if not _HAS_COLOR_SCHEME:
        assert verdict is None  # Qt 6.4: nessuna API, nessuna invenzione
        return
    scheme = qapp.styleHints().colorScheme()
    expected = {Qt.ColorScheme.Dark: True, Qt.ColorScheme.Light: False}.get(scheme)
    assert verdict == expected


@pytest.mark.skipif(sys.platform != "win32", reason="registro di Windows")
def test_windows_registry_is_read_like_the_system_does():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, theme._WIN_PERSONALIZE.split("\\", 1)[1]) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except FileNotFoundError:
        assert theme.windows_apps_dark() is None
        return
    assert theme.windows_apps_dark() is (value == 0)


def test_windows_registry_ignored_elsewhere(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert theme.windows_apps_dark() is None


@pytest.fixture()
def system_palette(qapp):
    """Simula un sistema con la palette data, come la trova l'app al primo
    avvio; alla fine rimette quella di prima."""
    before_palette = qapp.palette()
    before_cached = qapp.property(theme._SYSTEM_DARK_PROPERTY)

    def apply(window: str) -> None:
        qapp.setProperty(theme._SYSTEM_DARK_PROPERTY, None)
        qapp.setPalette(_palette(window))

    yield apply
    qapp.setPalette(before_palette)
    qapp.setProperty(theme._SYSTEM_DARK_PROPERTY, before_cached)


@pytest.mark.parametrize("window, dark", [("#1e1e1e", True), ("#f0f0f0", False)])
def test_qt64_fallback_uses_the_palette_read_before_ours(
    qapp, themed, system_palette, monkeypatch, window, dark
):
    """Il ramo di Qt 6.4 fuori da Windows (macOS, Linux): dopo apply_theme
    la palette dell'app è la NOSTRA, quindi il verdetto deve venire da
    quella di sistema letta prima, non da quella corrente."""
    monkeypatch.setattr(theme, "style_hints_dark", lambda _app: None)
    monkeypatch.setattr(theme, "windows_apps_dark", lambda: None)
    system_palette(window)
    chosen = themed()
    assert chosen is (theme.DARK if dark else theme.LIGHT)
    themed(theme.LIGHT if dark else theme.DARK)  # ora la palette corrente dice il contrario
    assert theme.system_prefers_dark(qapp) is dark


def test_style_hints_win_over_registry_and_palette(qapp, system_palette, monkeypatch):
    system_palette("#f0f0f0")
    monkeypatch.setattr(theme, "windows_apps_dark", lambda: False)
    monkeypatch.setattr(theme, "style_hints_dark", lambda _app: True)
    assert theme.system_prefers_dark(qapp) is True
    monkeypatch.setattr(theme, "style_hints_dark", lambda _app: None)
    monkeypatch.setattr(theme, "windows_apps_dark", lambda: True)
    assert theme.system_prefers_dark(qapp) is True  # Qt 6.4 su Windows: il registro


@pytest.mark.parametrize("dark", [True, False])
def test_apply_theme_follows_the_system(qapp, themed, monkeypatch, dark):
    monkeypatch.setattr(theme, "system_prefers_dark", lambda _app: dark)
    expected = theme.DARK if dark else theme.LIGHT
    assert themed() is expected
    assert qapp.palette().color(QPalette.ColorRole.Window) == QColor(expected.background)
    assert f"color: {expected.text}" in qapp.styleSheet()


@pytest.mark.skipif(not _HAS_COLOR_SCHEME, reason="Qt 6.4: il sistema non segnala il cambio")
def test_theme_follows_a_live_system_change(qapp, themed, monkeypatch):
    monkeypatch.setattr(theme, "system_prefers_dark", lambda _app: False)
    assert themed() is theme.LIGHT
    monkeypatch.setattr(theme, "system_prefers_dark", lambda _app: True)
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
    qapp.processEvents()
    assert qapp.palette().color(QPalette.ColorRole.Window) == QColor(theme.DARK.background)
