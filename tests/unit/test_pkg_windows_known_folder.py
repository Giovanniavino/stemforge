"""Le cartelle utente si chiedono a Windows, non a %USERPROFILE% (§9.7, OneDrive).

OneDrive "Backup delle cartelle" sposta Desktop, Documenti, Immagini (e
nelle versioni recenti Musica) sotto %OneDrive%: chi ricostruisce il
percorso da Path.home() scrive in una cartella che Esplora risorse non
mostra più. Qui si controlla che known_folder() dia esattamente ciò che
Windows registra in "User Shell Folders", anche quando è reindirizzata.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="cartelle note: solo Windows")

ROOT = Path(__file__).resolve().parents[2]
# nomi dei valori sotto User Shell Folders, che per ragioni storiche non sono i GUID
_REGISTRY_NAMES = {"MUSIC": "My Music", "DESKTOP": "Desktop"}


@pytest.fixture(scope="module")
def wi(request: pytest.FixtureRequest):
    sys.path.insert(0, str(ROOT / "packaging" / "windows"))
    request.addfinalizer(lambda: sys.path.remove(str(ROOT / "packaging" / "windows")))
    import windows_integration

    return windows_integration


def _registered(name: str) -> Path:
    import winreg

    key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
        raw = winreg.QueryValueEx(handle, name)[0]
    return Path(os.path.expandvars(raw))


@pytest.mark.parametrize("folder", sorted(_REGISTRY_NAMES))
def test_known_folder_matches_what_windows_registers(wi, folder: str):
    found = wi.known_folder(getattr(wi, f"FOLDERID_{folder}"))
    assert os.path.normcase(found) == os.path.normcase(_registered(_REGISTRY_NAMES[folder]))
    assert found.is_dir()


def test_unknown_folder_id_is_an_error_not_a_guess(wi):
    with pytest.raises(OSError):
        wi.known_folder("00000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize("folder", sorted(_REGISTRY_NAMES))
def test_qt_standard_paths_follow_the_redirection(wi, folder: str):
    """La correzione proposta per ui/app.py (Musica vera, non Path.home()/Music)
    si regge su QStandardPaths: qui si prova che Qt chiede a Windows e non
    ricostruisce il percorso, anche per una cartella spostata da OneDrive
    (sul dev-box lo è il Desktop)."""
    from PySide6.QtCore import QStandardPaths

    locations = {"MUSIC": QStandardPaths.MusicLocation, "DESKTOP": QStandardPaths.DesktopLocation}
    from_qt = Path(QStandardPaths.writableLocation(locations[folder]))
    expected = wi.known_folder(getattr(wi, f"FOLDERID_{folder}"))
    assert os.path.normcase(from_qt) == os.path.normcase(expected)


def test_virtualized_localappdata_tells_where_writes_really_go(wi, tmp_path: Path):
    """Il report dell'installer dichiara se gira in un contenitore MSIX:
    la risposta deve coincidere con dove finisce davvero una scrittura."""
    local = Path(os.environ["LOCALAPPDATA"])
    before = set(local.glob("stemforge-probe-*"))
    redirected = wi.virtualized_localappdata()
    assert set(local.glob("stemforge-probe-*")) == before, "la sonda non va lasciata in giro"
    marker = local / f"stemforge-test-{tmp_path.name}"
    marker.mkdir()
    try:
        copies = list((local / "Packages").glob(f"*/LocalCache/Local/{marker.name}"))
    finally:
        marker.rmdir()
    assert (redirected is None) == (not copies)
    if redirected is not None:
        assert os.path.normcase(copies[0].parent) == os.path.normcase(redirected)
