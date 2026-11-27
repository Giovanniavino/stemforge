"""Convenzioni del sistema, diagnostica e drag (BUILD_SPEC §7.2, §7.4,
§8.6, §9.9).

I moduli di altre aree (worker/diagnostics.py, ui/drag_export.py) qui
si sostituiscono con moduli finti in sys.modules: si verifica il
contratto (chi chiama cosa, con quali argomenti), non la loro logica.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
from test_ui_support import (  # noqa: F401  (fixture)
    isolated_settings,
    language,
    make_window,
    qapp,
    write_manifest,
)

from PySide6.QtCore import QMimeData, QStandardPaths, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from stemforge.ui import conventions, diagnostics_action, result_view

_DIAGNOSTICS_MODULE = "stemforge.worker.diagnostics"
_DRAG_MODULE = "stemforge.ui.drag_export"


# -- "Mostra nel Finder" e Cmd/Ctrl (§7.4, §8.6) ----------------------------


@pytest.mark.parametrize("platform, italian, english", [
    ("darwin", "Mostra nel Finder", "Show in Finder"),
    ("win32", "Mostra in Esplora file", "Show in File Explorer"),
    ("linux", "Mostra nella cartella", "Show in Folder"),
])
def test_reveal_label_follows_the_system(qapp, language, platform, italian, english):
    language("it")
    assert conventions.reveal_label(platform) == italian
    language("en")
    assert conventions.reveal_label(platform) == english


def test_result_screen_uses_this_system_label(qapp, language, tmp_path):
    language("it")
    view = result_view.ResultView()
    expected = {"darwin": "Mostra nel Finder", "win32": "Mostra in Esplora file"}
    assert view._reveal_button.text() == expected.get(sys.platform, "Mostra nella cartella")


@pytest.mark.parametrize("platform, command", [
    ("darwin", ["open", "-R"]),
    ("win32", ["explorer", "/select,"]),
])
def test_reveal_highlights_the_selected_stem(qapp, tmp_path, monkeypatch, platform, command):
    launched: list[list[str]] = []
    monkeypatch.setattr(result_view.subprocess, "Popen", launched.append)
    view = result_view.ResultView()
    out = tmp_path / "out" / "brano"
    view.show_result(out, write_manifest(out), [])
    view.list.setCurrentRow(1)
    # solo il modulo sotto test vede l'altro sistema, non tutta la suite
    monkeypatch.setattr(result_view, "sys", types.SimpleNamespace(platform=platform))
    view._reveal()
    monkeypatch.undo()
    assert launched == [command + [str(out / "drums.wav")]]


# -- cartella di output: la Musica vera del sistema --------------------------


def test_output_folder_is_the_system_music_folder():
    music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation)
    assert music, "il sistema non dichiara una cartella Musica"
    assert conventions.default_output_dir() == Path(music) / "StemForge"


def test_output_folder_is_asked_to_the_system_not_guessed(monkeypatch, tmp_path):
    """Una Musica spostata (OneDrive, altro disco) non sta sotto la home:
    la cartella deve venire da QStandardPaths anche quando è altrove.
    Su questo PC Musica non è spostata, quindi lo spostamento si simula."""
    moved = tmp_path / "OneDrive" / "Musica"

    class MovedMusic(QStandardPaths):
        @staticmethod
        def writableLocation(location):  # noqa: N802
            assert location == QStandardPaths.StandardLocation.MusicLocation
            return str(moved)

    monkeypatch.setattr(conventions, "QStandardPaths", MovedMusic)
    assert conventions.default_output_dir() == moved / "StemForge"


@pytest.mark.skipif(sys.platform != "win32", reason="cartelle note di Windows")
def test_output_folder_follows_onedrive_redirection():
    """Il confronto è con la cartella nota chiesta a Windows stesso
    (SHGetKnownFolderPath), che segue lo spostamento su OneDrive o su un
    altro disco: `~/Music` scritto a mano qui fallirebbe."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                    ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    # FOLDERID_Music {4BD8D571-6D19-48D3-BE97-422220080E43}
    music_id = GUID(0x4BD8D571, 0x6D19, 0x48D3,
                    (ctypes.c_ubyte * 8)(0xBE, 0x97, 0x42, 0x22, 0x20, 0x08, 0x0E, 0x43))
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    assert shell32.SHGetKnownFolderPath(ctypes.byref(music_id), 0, None, ctypes.byref(out)) == 0
    known = Path(out.value)
    ctypes.windll.ole32.CoTaskMemFree(out)
    assert os.path.normcase(conventions.default_output_dir()) == os.path.normcase(
        known / "StemForge"
    )


# -- Esporta diagnostica (§9.9) ---------------------------------------------


@pytest.fixture()
def fake_diagnostics(monkeypatch, tmp_path: Path):
    """Il modulo dell'area E, finto: registra la cartella e crea lo zip."""
    calls: list[Path] = []

    def export_diagnostics(dest_dir: Path) -> Path:
        calls.append(dest_dir)
        archive = dest_dir / "stemforge-diagnostica.zip"
        archive.write_bytes(b"PK\x05\x06" + b"\0" * 18)
        return archive

    module = types.ModuleType(_DIAGNOSTICS_MODULE)
    module.export_diagnostics = export_diagnostics
    monkeypatch.setitem(sys.modules, _DIAGNOSTICS_MODULE, module)
    return calls


def _chosen_folder(monkeypatch, folder: Path | None) -> list[object]:
    asked: list[object] = []

    def ask(parent):
        asked.append(parent)
        return folder

    monkeypatch.setattr(diagnostics_action, "ask_folder", ask)
    return asked


def _finish(footer) -> None:
    footer.exporter.wait(10)
    QApplication.processEvents()  # l'esito torna dal thread come evento


def test_diagnostics_button_saves_where_the_user_chooses(
    qapp, language, fake_diagnostics, monkeypatch, tmp_path
):
    language("it")
    window = make_window(qapp, tmp_path)
    footer = window._drop.footer
    asked = _chosen_folder(monkeypatch, tmp_path)
    footer.diagnostics.click()
    _finish(footer)
    assert asked and fake_diagnostics == [tmp_path]
    assert footer.status.text() == (
        f"Diagnostica salvata: {tmp_path / 'stemforge-diagnostica.zip'}"
    )
    assert footer.diagnostics.isEnabled()
    window.close()


def test_diagnostics_cancelled_dialog_does_nothing(qapp, isolated_settings, fake_diagnostics, monkeypatch, tmp_path):
    window = make_window(qapp, tmp_path)
    footer = window._drop.footer
    _chosen_folder(monkeypatch, None)
    footer.diagnostics.click()
    _finish(footer)
    assert fake_diagnostics == []
    assert footer.status.text() == ""
    window.close()


def test_diagnostics_failure_is_shown_not_lost(qapp, language, monkeypatch, tmp_path):
    def broken(_dest: Path) -> Path:
        raise OSError("disco pieno")

    module = types.ModuleType(_DIAGNOSTICS_MODULE)
    module.export_diagnostics = broken
    monkeypatch.setitem(sys.modules, _DIAGNOSTICS_MODULE, module)
    language("it")
    window = make_window(qapp, tmp_path)
    footer = window._drop.footer
    _chosen_folder(monkeypatch, tmp_path)
    footer.diagnostics.click()
    _finish(footer)
    assert footer.status.text() == "Non sono riuscito a esportare la diagnostica: disco pieno"
    assert footer.diagnostics.isEnabled()
    window.close()


def test_diagnostics_missing_module_is_explained(qapp, language, monkeypatch, tmp_path):
    """Senza il modulo del worker (pacchetto rotto, o area E non ancora
    integrata) il pulsante lo dice, invece di non fare niente."""
    monkeypatch.setitem(sys.modules, _DIAGNOSTICS_MODULE, None)  # import -> ImportError
    language("it")
    window = make_window(qapp, tmp_path)
    asked = _chosen_folder(monkeypatch, tmp_path)
    window._drop.footer.diagnostics.click()
    QApplication.processEvents()
    assert asked == []
    assert "non è disponibile" in window._drop.footer.status.text()
    window.close()


def test_help_menu_exports_diagnostics(qapp, language, fake_diagnostics, monkeypatch, tmp_path):
    """La voce del menu Aiuto di macOS: qui si installa a mano per
    provarla anche su Windows e Linux."""
    language("it")
    window = make_window(qapp, tmp_path)
    if window._help_menu is None:
        window.install_help_menu()
    assert window._help_menu.title() == "&Aiuto"
    assert window._diagnostics_action.text() == "Esporta diagnostica…"
    # resta nel menu Aiuto: Qt non la sposta nel menu dell'app
    assert window._diagnostics_action.menuRole() == QAction.MenuRole.NoRole
    _chosen_folder(monkeypatch, tmp_path)
    window._diagnostics_action.trigger()
    _finish(window._drop.footer)
    assert fake_diagnostics == [tmp_path]
    language("en")
    assert window._help_menu.title() == "&Help"
    window.close()


def test_help_menu_only_on_macos(qapp, isolated_settings, tmp_path):
    window = make_window(qapp, tmp_path)
    assert (window._help_menu is not None) == (sys.platform == "darwin")
    window.close()


# -- drag out: il contenuto lo costruisce ui/drag_export.py (§7.2) ----------


class _FakeDrag:
    made: list[_FakeDrag] = []

    def __init__(self, source) -> None:
        self.source = source
        self.mime: QMimeData | None = None
        self.action = None
        _FakeDrag.made.append(self)

    def setMimeData(self, mime: QMimeData) -> None:  # noqa: N802
        self.mime = mime

    def setPixmap(self, _pixmap) -> None:  # noqa: N802
        pass

    def setHotSpot(self, _point) -> None:  # noqa: N802
        pass

    def exec(self, action):
        self.action = action
        return action


def test_drag_uses_drag_export_with_every_selected_stem(qapp, monkeypatch, tmp_path):
    built: list[list[Path]] = []

    def build_mime_data(paths: list[Path]) -> QMimeData:
        built.append(list(paths))
        return QMimeData()

    module = types.ModuleType(_DRAG_MODULE)
    module.build_mime_data = build_mime_data
    monkeypatch.setitem(sys.modules, _DRAG_MODULE, module)
    _FakeDrag.made = []
    monkeypatch.setattr(result_view, "QDrag", _FakeDrag)

    view = result_view.ResultView()
    out = tmp_path / "out" / "brano"
    view.show_result(out, write_manifest(out), [])
    view.list.selectAll()
    view.list.startDrag(Qt.DropAction.CopyAction)

    assert built == [[out / "vocals.wav", out / "drums.wav", out / "bass.wav"]]
    assert all(path.is_absolute() for path in built[0])
    (drag,) = _FakeDrag.made
    assert drag.mime is not None
    assert drag.action == Qt.DropAction.CopyAction  # Copy, mai Move


def test_drag_keeps_the_list_order_not_the_click_order(qapp, monkeypatch, tmp_path):
    """Selezionando basso e poi voce, le tracce arrivano nella DAW come
    sono nell'elenco: voce prima di basso."""
    built: list[list[Path]] = []
    module = types.ModuleType(_DRAG_MODULE)
    module.build_mime_data = lambda paths: built.append(list(paths)) or QMimeData()
    monkeypatch.setitem(sys.modules, _DRAG_MODULE, module)
    _FakeDrag.made = []
    monkeypatch.setattr(result_view, "QDrag", _FakeDrag)

    view = result_view.ResultView()
    out = tmp_path / "out" / "brano"
    view.show_result(out, write_manifest(out), [])
    view.list.clearSelection()
    view.list.item(2).setSelected(True)
    view.list.item(0).setSelected(True)
    # Qt dà l'ordine dei clic: è quello che la lista deve correggere
    assert [view.list.row(i) for i in view.list.selectedItems()] == [2, 0]
    view.list.startDrag(Qt.DropAction.CopyAction)
    assert built == [[out / "vocals.wav", out / "bass.wav"]]


def test_drag_without_selection_starts_nothing(qapp, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, _DRAG_MODULE, None)  # non deve servire
    _FakeDrag.made = []
    monkeypatch.setattr(result_view, "QDrag", _FakeDrag)
    view = result_view.ResultView()
    view.list.startDrag(Qt.DropAction.CopyAction)
    assert _FakeDrag.made == []
