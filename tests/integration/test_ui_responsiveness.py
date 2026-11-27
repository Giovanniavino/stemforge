"""Reattività dell'interfaccia: il thread principale non si blocca.

docs/optimization/O4.md. La strumentazione vive qui, non nel codice di
produzione: una sentinella QTimer registra ogni buco oltre 50 ms mentre
si fa quello che fa l'utente (drop, scelta, job, risultato).
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QElapsedTimer, QMimeData, QPointF, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from test_ui_support import make_window, qapp, wait_for_probe  # noqa: E402,F401

BLOCK_MS = 50  # oltre, il blocco si registra
# Il test fallisce solo oltre questo: i runner CI sono più lenti del
# dev-box (l'avvio del QProcess da solo vale 30-55 ms qui), ma un probe
# FFmpeg o una scansione sul thread dell'UI lo superano comunque.
BUDGET_MS = 150
SLOW_PROBE_S = 0.4  # il FFmpeg di un m4a su un Mac lento
CHILD = Path(__file__).parent / "ui_job_child.py"


class Sentinel:
    """Un QTimer da 5 ms: se scatta tardi, il thread principale era fermo."""

    INTERVAL_MS = 5

    def __init__(self) -> None:
        self.label = "idle"
        self.blocks: list[tuple[str, int]] = []
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0
        self._timer = QTimer()
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        now = self._clock.elapsed()
        gap = now - self._last - self.INTERVAL_MS
        if gap > BLOCK_MS:
            self.blocks.append((self.label, gap))
        self._last = now

    def act(self, label: str, action) -> None:
        """Un gesto dell'utente, poi l'event loop libero come fra due gesti."""
        self.label = label
        self._last = self._clock.elapsed()
        action()
        QTest.qWait(30)

    def stop(self) -> None:
        self._timer.stop()


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
    # Windows senza privilegi per i link: il resto del confronto vale lo stesso
    with contextlib.suppress(OSError):
        (tmp_path / "link").symlink_to(tmp_path / "z", target_is_directory=True)
    dropped = [tmp_path, tmp_path / "b.wav", tmp_path / "cover.jpg"]

    assert _collect_audio_files(dropped) == _rglob_reference(dropped)
    accepted, _ = _collect_audio_files([tmp_path])
    assert tmp_path / "out" / "brano" / "vocals.wav" not in accepted
    assert tmp_path / "out" / "brano" / "sub" / "x.wav" in accepted


def _drop(window, paths: list[Path]) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    window._drop.dropEvent(QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


@pytest.fixture()
def slow_probe(monkeypatch: pytest.MonkeyPatch):
    """La durata arriva dopo SLOW_PROBE_S, come dal processo FFmpeg; si
    annota da quale thread è stata chiesta."""
    from stemforge.worker import planning

    threads: list[threading.Thread] = []

    def probe(path: Path) -> float:
        threads.append(threading.current_thread())
        time.sleep(SLOW_PROBE_S)
        return 123.0 if path.stem == "brano" else 45.0

    monkeypatch.setattr(planning, "probe_duration", probe)
    return threads


def test_drop_does_not_wait_for_the_probe(qapp, tmp_path: Path, slow_probe):
    window = make_window(qapp, tmp_path)
    first, second = tmp_path / "primo.wav", tmp_path / "brano.wav"
    for song in (first, second):
        song.touch()

    started = time.perf_counter()
    _drop(window, [first])
    assert time.perf_counter() - started < SLOW_PROBE_S / 2
    assert window._stack.currentWidget() is window._drop  # niente picker a metà
    _drop(window, [second])  # un secondo drop prima della durata del primo
    wait_for_probe(window)
    QTest.qWait(int(SLOW_PROBE_S * 1000))  # anche il probe vecchio ha risposto

    assert window._stack.currentWidget() is window._picker
    assert window._picker._source == second  # vale l'ultimo drop
    assert window._picker._duration == 123.0
    assert threading.main_thread() not in slow_probe
    window.close()


@pytest.mark.perf  # ~7 s: il worker finto importa torch nel processo figlio
def test_main_thread_never_blocks(qapp, tmp_path: Path, mix_44k: Path, slow_probe,
                                  monkeypatch: pytest.MonkeyPatch):
    """Drop, scelta, job (QProcess vero, worker finto), risultato: nessun
    blocco oltre BUDGET_MS; quelli oltre 50 ms si stampano (pytest -s)."""
    from stemforge.model.stem import StemKind
    from stemforge.ui import bridge

    monkeypatch.setattr(bridge, "worker_command", lambda: [sys.executable, str(CHILD)])
    song = mix_44k
    folder = tmp_path / "cartella"
    folder.mkdir()
    for index in range(300):  # un batch grande: la scansione resta sotto budget
        (folder / f"t{index}.{'jpg' if index % 3 else 'wav'}").touch()
    window = make_window(qapp, tmp_path)
    picker = window._picker
    sentinel = Sentinel()

    sentinel.act("drop cartella", lambda: _drop(window, [folder]))
    wait_for_probe(window)
    sentinel.act("indietro", window._show_drop)
    sentinel.act("drop", lambda: _drop(window, [song]))
    wait_for_probe(window)
    sentinel.act("spunta", lambda: picker._boxes[StemKind.GUITAR].toggle())
    sentinel.act("tutto", picker._select_all)
    sentinel.act("solo voce", picker._select_vocals_only)
    sentinel.act("qualità", lambda: picker._quality.setCurrentIndex(2))
    sentinel.act("separa", picker.request_start)
    sentinel.label = "job"
    deadline = time.monotonic() + 60
    while window._stack.currentWidget() is not window._result:
        assert time.monotonic() < deadline, "il job finto non è mai finito"
        QTest.qWait(10)
    sentinel.label = "risultato"
    QTest.qWait(100)
    sentinel.stop()
    window.close()

    print("\nblocchi del thread principale oltre 50 ms:", sentinel.blocks or "nessuno")
    assert window._result.list.count() == 1  # il job è arrivato davvero alla fine
    slow = [(label, ms) for label, ms in sentinel.blocks if ms > BUDGET_MS]
    assert not slow, f"thread principale fermo oltre {BUDGET_MS} ms: {slow}"
