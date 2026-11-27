"""Reattività dell'interfaccia: il thread principale non si blocca.

docs/optimization/O4.md. La strumentazione vive qui, non nel codice di
produzione: una sentinella QTimer registra ogni buco oltre 50 ms mentre
si fa quello che fa l'utente (drop, scelta, job, risultato).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _rglob_reference(paths: list[Path]) -> tuple[list[Path], int]:
    """La raccolta com'era prima di O4 (rglob + due stat per voce)."""
    from stemforge.ui.drop_zone import is_supported

    accepted: list[Path] = []
    rejected = 0
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if (child.parent / "manifest.json").is_file():
                    continue
                if child.is_file():
                    if is_supported(child):
                        accepted.append(child)
                    else:
                        rejected += 1
        elif is_supported(path):
            accepted.append(path)
        else:
            rejected += 1
    return accepted, rejected


def test_folder_scan_matches_rglob(tmp_path: Path):
    from stemforge.ui.drop_zone import _collect_audio_files

    for name in ("b.wav", "A.FLAC", "cover.jpg", "z/a.mp3", "z/y/deep.m4a", "z/y/notes.txt",
                 "out/brano/vocals.wav", "out/brano/manifest.json", "out/brano/sub/x.wav",
                 "Ä/ü.wav"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).touch()
    (tmp_path / "dir.wav").mkdir()  # una cartella con un nome da audio non è un file
    (tmp_path / "vuota").mkdir()
    try:
        (tmp_path / "link").symlink_to(tmp_path / "z", target_is_directory=True)
    except OSError:  # Windows senza privilegi per i link: il resto vale lo stesso
        pass
    dropped = [tmp_path, tmp_path / "b.wav", tmp_path / "cover.jpg"]

    assert _collect_audio_files(dropped) == _rglob_reference(dropped)
    accepted, _ = _collect_audio_files([tmp_path])
    assert tmp_path / "out" / "brano" / "vocals.wav" not in accepted
    assert tmp_path / "out" / "brano" / "sub" / "x.wav" in accepted
