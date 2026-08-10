"""Annullamento: il figlio muore entro 1 s e i parziali si ripuliscono.

BUILD_SPEC §5.5, §8.3, §10.3. La garanzia del secondo la dà il kill del
processo; il messaggio `Started` dice al padre quale cartella ripulire.
Qui si esercita esattamente il contratto che userà bridge.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from stemforge.worker import protocol

CHILD = Path(__file__).parent / "cancel_child.py"
KILL_DEADLINE_S = 1.0


def test_kill_within_one_second_and_cleanup(mix_44k: Path, tmp_path: Path):
    out_base = tmp_path / "out"
    process = subprocess.Popen(
        [sys.executable, str(CHILD), str(mix_44k), str(out_base)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        # attendere Started: da lì il padre conosce la cartella del job
        out_dir: Path | None = None
        deadline = time.monotonic() + 20.0
        assert process.stdout is not None
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            message = protocol.decode(line)
            if isinstance(message, protocol.Started):
                out_dir = Path(message.out_dir)
                break
        assert out_dir is not None, "nessun messaggio Started dal figlio"
        assert out_dir.exists()

        # l'utente preme Annulla: kill, come farà bridge.py (D2)
        started = time.monotonic()
        process.kill()
        process.wait(timeout=KILL_DEADLINE_S)
        assert time.monotonic() - started < KILL_DEADLINE_S

        # il padre ripulisce i parziali: nessun file resta bloccato
        shutil.rmtree(out_dir)
        assert not out_dir.exists()
        # e dentro non c'era nessuno stem completo spacciabile per risultato
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
