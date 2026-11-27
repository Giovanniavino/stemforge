"""engine/ffmpeg._run con un processo finto che non collabora (D9).

Al posto di ffmpeg gira un Python che dorme senza leggere stdin: il
tempo limite deve scattare lo stesso e il processo deve morire.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from stemforge.engine import ffmpeg

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
# molto piu' del buffer di una pipe (64 KiB): write() si blocca di sicuro
STUCK_INPUT = bytes(32 * 1024 * 1024)
TIMEOUT_S = 0.5
# margine largo per una macchina carica, ma ben sotto i 60 s del dormiente
MAX_ELAPSED_S = 20.0


@pytest.fixture()
def sleeper(monkeypatch, tmp_path):
    started: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def fake_popen(args, **kwargs):
        started.append(real_popen(SLEEPER, **kwargs))
        return started[-1]

    monkeypatch.setattr(ffmpeg, "_require", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "Popen", fake_popen)
    return started


def test_timeout_fires_even_if_ffmpeg_never_reads_stdin(sleeper):
    began = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        ffmpeg._run(["-i", "pipe:0"], TIMEOUT_S, stdin=STUCK_INPUT)
    assert time.monotonic() - began < MAX_ELAPSED_S
    assert len(sleeper) == 1 and sleeper[0].poll() is not None


def test_timeout_without_stdin_kills_the_process(sleeper):
    with pytest.raises(subprocess.TimeoutExpired):
        ffmpeg._run(["-version"], TIMEOUT_S)
    assert sleeper[0].poll() is not None
