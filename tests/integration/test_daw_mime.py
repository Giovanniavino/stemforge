"""Contenuto MIME del drag verso le DAW, per ogni sistema simulato (§7.2.1).

Non serve una QApplication: QMimeData e QUrl stanno in QtCore. I percorsi
hanno unicode, spazi e caratteri che in un URL vanno codificati (#, %, [).
"""

from __future__ import annotations

import inspect
import logging
import ntpath
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from stemforge.ui import drag_export  # noqa: E402
from stemforge.ui.drag_export import (  # noqa: E402
    URI_LIST,
    build_mime_data,
    drop_paths,
    mime_for_platform,
    normalize_path,
    strip_verbatim,
)

WIN_FILES = ["C:\\Musica\\Brano con spazi è 日本\\vocals.wav",
             "C:\\Musica\\Brano #1 [mix] 100%\\drums.wav"]
POSIX_FILES = ["/Users/ana/Music/StemForge/Brano con spazi è 日本/vocals.wav",
               "/home/ana/Musica/Brano #1 [mix] 100%/drums.wav"]
_ON_WINDOWS = sys.platform == "win32"


def test_signature_is_the_one_result_view_imports():
    signature = inspect.signature(build_mime_data)
    assert list(signature.parameters) == ["paths"]
    assert signature.parameters["paths"].annotation == "list[Path]"
    assert signature.return_annotation == "QMimeData"


def test_windows_mime_is_file_urls_only():
    mime = mime_for_platform(WIN_FILES, "win32")
    # un solo formato: è la condizione perché il drag di Qt offra CF_HDROP
    # e rifiuti testo e UniformResourceLocator (qwindowsdropdataobject.cpp)
    assert mime.formats() == [URI_LIST]
    assert mime.hasUrls()
    urls = mime.urls()
    assert all(url.isLocalFile() for url in urls)
    assert [url.scheme() for url in urls] == ["file", "file"]
    back = [ntpath.normpath(url.toLocalFile()) for url in urls]
    assert back == WIN_FILES
    assert urls[0].toString().startswith("file:///C:/Musica/")


def test_windows_unc_share_becomes_url_host():
    mime = mime_for_platform(["\\\\nas\\stem\\Brano è\\bass.wav"], "win32")
    url = mime.urls()[0]
    assert url.host() == "nas"
    assert url.isLocalFile()
    assert ntpath.normpath(url.toLocalFile()) == "\\\\nas\\stem\\Brano è\\bass.wav"


def test_macos_mime_is_file_urls_only():
    mime = mime_for_platform(POSIX_FILES, "darwin")
    assert mime.formats() == [URI_LIST]
    assert [url.toLocalFile() for url in mime.urls()] == POSIX_FILES


@pytest.mark.parametrize("platform", ["linux", "freebsd14"])
def test_linux_has_explicit_crlf_uri_list(platform: str):
    mime = mime_for_platform(POSIX_FILES, platform)
    assert mime.formats() == [URI_LIST]
    payload = bytes(mime.data(URI_LIST))
    lines = payload.split(b"\r\n")
    assert lines[-1] == b"", "ogni riga chiusa da CRLF, anche l'ultima"
    assert lines[:-1] == [
        b"file:///Users/ana/Music/StemForge/Brano%20con%20spazi%20%C3%A8%20"
        b"%E6%97%A5%E6%9C%AC/vocals.wav",
        b"file:///home/ana/Musica/Brano%20%231%20%5Bmix%5D%20100%25/drums.wav",
    ]
    # SWELL (REAPER su Linux) accetta solo righe che iniziano con file://
    assert all(line.startswith(b"file://") for line in lines[:-1])
    # RFC 3986 per il path: solo unreserved, "/" e escape %XX
    allowed = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/%")
    assert all(set(line[len(b"file://"):]) <= allowed for line in lines[:-1])
    # e il payload esplicito resta leggibile come URL dallo stesso Qt
    assert [url.toLocalFile() for url in mime.urls()] == POSIX_FILES


def test_no_files_no_urls():
    for platform in ("win32", "darwin", "linux"):
        mime = mime_for_platform([], platform)
        assert not mime.hasUrls()
        assert mime.formats() == []


@pytest.mark.parametrize(("raw", "expected"), [
    ("\\\\?\\C:\\Musica\\x\\..\\vocals.wav", "C:\\Musica\\vocals.wav"),
    ("\\\\?\\UNC\\nas\\stem\\bass.wav", "\\\\nas\\stem\\bass.wav"),
    ("\\\\?\\unc\\nas\\stem\\bass.wav", "\\\\nas\\stem\\bass.wav"),
    ("C:/Musica/./Brano è/vocals.wav", "C:\\Musica\\Brano è\\vocals.wav"),
    ("\\\\nas\\stem\\bass.wav", "\\\\nas\\stem\\bass.wav"),
])
def test_windows_paths_lose_verbatim_prefix(raw: str, expected: str):
    assert normalize_path(raw, "win32") == expected


def test_strip_verbatim_leaves_normal_paths_alone():
    assert strip_verbatim("C:\\x\\y.wav") == "C:\\x\\y.wav"
    assert strip_verbatim("\\\\nas\\x.wav") == "\\\\nas\\x.wav"


def test_posix_paths_are_absolute_and_normalized():
    assert normalize_path("/Users/ana/./Music/x/../vocals.wav", "darwin") == \
        "/Users/ana/Music/vocals.wav"
    # su POSIX la barra rovescia è un carattere del nome, non un separatore
    assert normalize_path("/tmp/a\\b.wav", "linux") == "/tmp/a\\b.wav"


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")
    return path


def test_drop_paths_keeps_existing_files_in_order(tmp_path: Path, caplog):
    vocals = _touch(tmp_path / "Brano con spazi è" / "vocals.wav")
    drums = _touch(tmp_path / "Brano con spazi è" / "drums.wav")
    missing = tmp_path / "Brano con spazi è" / "bass.wav"
    folder = tmp_path / "Brano con spazi è"
    with caplog.at_level(logging.WARNING, logger="stemforge"):
        got = drop_paths([drums, missing, vocals, folder, drums])
    assert got == [os.path.abspath(drums), os.path.abspath(vocals)]
    assert caplog.text.count("escluso") == 2


def test_drop_paths_makes_relative_paths_absolute(tmp_path: Path, monkeypatch):
    _touch(tmp_path / "out" / "other.wav")
    monkeypatch.chdir(tmp_path)
    got = drop_paths([Path("out") / "x" / ".." / "other.wav"])
    assert got == [str(tmp_path / "out" / "other.wav")]
    assert os.path.isabs(got[0])


def test_build_mime_data_on_this_system(tmp_path: Path):
    vocals = _touch(tmp_path / "Brano è 日本" / "vocals.wav")
    mime = build_mime_data([vocals, tmp_path / "manca.wav"])
    assert mime.formats() == [URI_LIST]
    urls = mime.urls()
    assert len(urls) == 1
    assert os.path.normpath(urls[0].toLocalFile()) == str(vocals)
    assert build_mime_data([]).hasUrls() is False


@pytest.mark.skipif(not _ON_WINDOWS, reason="MAX_PATH esiste solo su Windows")
def test_long_windows_path_is_shortened_never_verbatim(tmp_path: Path, caplog):
    folder = "\\\\?\\" + str(tmp_path.joinpath(*(["cartella lunghissima àèì"] * 12)))
    os.makedirs(folder)
    with open(folder + "\\vocals.wav", "wb") as handle:
        handle.write(b"RIFF")
    long_path = drag_export.strip_verbatim(folder) + "\\vocals.wav"
    assert len(long_path) >= drag_export.WIN_MAX_PATH
    with caplog.at_level(logging.WARNING, logger="stemforge"):
        got = drop_paths([Path(long_path)])
    assert len(got) == 1
    assert not got[0].startswith("\\\\?\\")
    assert ntpath.basename(got[0]) == "vocals.wav"
    if len(got[0]) < drag_export.WIN_MAX_PATH:
        assert os.path.samefile(got[0], "\\\\?\\" + long_path)
    else:
        # volume senza nomi 8.3: si consegna il percorso lungo, ma lo si dice
        assert got[0] == long_path
        assert "oltre" in caplog.text
