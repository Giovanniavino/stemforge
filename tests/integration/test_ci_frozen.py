"""La batteria contro l'app impacchettata (BUILD_SPEC §10.5, §10.6: `frozen`).

I guasti peggiori visti sul campo esistevano solo dentro il pacchetto:
qui si lancia l'eseguibile vero, come lo lancia l'utente o l'app stessa.

    STEMFORGE_FROZEN_EXE=<eseguibile> pytest -m frozen

L'eseguibile e' StemForge.app/Contents/MacOS/StemForge (anche dal DMG
montato), StemForge.exe (anche quello installato) o l'AppImage. Senza la
variabile i test si saltano; con la variabile ma senza file falliscono.

Il fixture m4a si genera con un FFmpeg LGPL (D9): STEMFORGE_FFMPEG (file
o cartella, come per l'app) oppure quello dentro il pacchetto. Al
processo dell'app STEMFORGE_FFMPEG si toglie: deve bastare il suo.
Con STEMFORGE_FROZEN_STRICT=1 (la CI) un encoder introvabile e' un
errore, non un salto.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K
from stemforge.worker import protocol
from tests.conftest import write_fixture

pytestmark = pytest.mark.frozen

ENV_EXE = "STEMFORGE_FROZEN_EXE"
ENV_FFMPEG = "STEMFORGE_FFMPEG"
ENV_STRICT = "STEMFORGE_FROZEN_STRICT"
# l'avvio a freddo di un pacchetto con torch su un runner macOS supera il
# mezzo minuto; il collaudo offline decodifica cinque formati in piu'
SELFTEST_TIMEOUT_S = 15 * 60
STARTED_TIMEOUT_S = 5 * 60
ERROR_TIMEOUT_S = 5 * 60
KILL_DEADLINE_S = 1.0  # §8.3: Annulla ferma il lavoro entro un secondo
FIXTURE_SECONDS = 3.0
ENCODE_TIMEOUT_S = 120


@pytest.fixture(scope="module")
def frozen_exe() -> Path:
    raw = os.environ.get(ENV_EXE, "").strip()
    if not raw:
        pytest.skip(f"{ENV_EXE} non impostata: nessuna app impacchettata da collaudare")
    exe = Path(raw).resolve()
    if not exe.is_file():
        pytest.fail(f"{ENV_EXE} punta a un file che non c'e': {exe}")
    return exe


def _app_env() -> dict[str, str]:
    """L'ambiente dell'app: senza scorciatoie verso un FFmpeg esterno."""
    env = dict(os.environ)
    env.pop(ENV_FFMPEG, None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    # nei container non c'e' FUSE: il runtime type2 estrae e lancia
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    return env


def _popen(exe: Path, *args: str) -> subprocess.Popen[str]:
    # gruppo di processi a parte: un'AppImage e' un runtime che lancia
    # l'app come figlio, e il kill deve prendere entrambi
    extra = {} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen(
        [str(exe), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        env=_app_env(), **extra,
    )


def _kill(process: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # gia' uscito da solo (es. dopo un errore): niente da fermare


def _messages(process: subprocess.Popen[str]) -> queue.Queue[protocol.Message | None]:
    """Messaggi del worker su una coda; None quando stdout si chiude."""
    found: queue.Queue[protocol.Message | None] = queue.Queue()

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            if (message := protocol.decode(line)) is not None:
                found.put(message)
        found.put(None)

    threading.Thread(target=pump, daemon=True).start()
    return found


def _wait_for(found: queue.Queue, kinds: tuple[type, ...], timeout_s: float):
    """Il primo messaggio di uno dei tipi dati, o None se il worker tace."""
    deadline = time.monotonic() + timeout_s
    while (left := deadline - time.monotonic()) > 0:
        try:
            message = found.get(timeout=left)
        except queue.Empty:
            return None
        if message is None or isinstance(message, kinds):
            return message
    return None


def _start_job(exe: Path, source: Path, out_base: Path) -> subprocess.Popen[str]:
    job = SeparationJob(
        source=source, wanted=(K.VOCALS,), quality="fast", out_dir=out_base, device="cpu",
    )
    process = _popen(exe, "--worker")
    assert process.stdin is not None
    process.stdin.write(job.to_json() + "\n")
    process.stdin.flush()
    return process


def _encoder(exe: Path) -> Path | None:
    raw = os.environ.get(ENV_FFMPEG, "").strip()
    if raw:
        path = Path(raw)
        return next((p for p in (path / "ffmpeg.exe", path / "ffmpeg") if p.is_file()), None) \
            if path.is_dir() else (path if path.is_file() else None)
    # nel pacchetto sta in <_MEIPASS>/ffmpeg/ (contratto dell'area FFmpeg)
    bundle = next((p for p in exe.parents if p.suffix == ".app"), exe.parent)
    return next((p for p in bundle.rglob("ffmpeg/ffmpeg*") if p.is_file()), None)


def _make_m4a(exe: Path, tmp_path: Path) -> Path:
    encoder = _encoder(exe)
    if encoder is None:
        message = f"nessun FFmpeg per creare il fixture m4a ({ENV_FFMPEG} o nel pacchetto)"
        if os.environ.get(ENV_STRICT) == "1":
            pytest.fail(message)
        pytest.skip(message)
    wav = write_fixture(tmp_path / "sorgente.wav", 44100, seconds=FIXTURE_SECONDS)
    m4a = tmp_path / "brano.m4a"
    subprocess.run(
        [str(encoder), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
         "-c:a", "aac", "-b:a", "128k", str(m4a)],
        check=True, timeout=ENCODE_TIMEOUT_S,
    )
    assert m4a.stat().st_size > 1000
    return m4a


def test_selftest_offline_passes(frozen_exe: Path, tmp_path: Path):
    report = tmp_path / "report.json"
    proc = subprocess.run(
        [str(frozen_exe), "--selftest", "--report", str(report), "--offline"],
        capture_output=True, text=True, errors="replace",
        timeout=SELFTEST_TIMEOUT_S, env=_app_env(),
    )
    assert report.is_file(), f"nessun report (uscita {proc.returncode}): {proc.stderr[-2000:]}"
    data = json.loads(report.read_text(encoding="utf-8"))
    failed = [c for c in data["checks"] if c["status"] == "fail"]
    assert not failed, failed
    assert data["ok"] and proc.returncode == 0
    statuses = {c["name"]: c["status"] for c in data["checks"]}
    assert statuses.get("decodifica dei formati") == "ok", statuses


def test_corrupt_file_gives_clear_error(frozen_exe: Path, tmp_path: Path):
    bad = tmp_path / "rotto.m4a"
    bad.write_bytes(b"questo non e' audio" * 100)
    process = _start_job(frozen_exe, bad, tmp_path / "out")
    try:
        found = _messages(process)
        message = _wait_for(found, (protocol.Error, protocol.Started), ERROR_TIMEOUT_S)
        assert isinstance(message, protocol.Error), f"atteso un errore, arrivato {message!r}"
        assert message.message.strip(), "errore senza messaggio per l'utente"
        assert "Traceback" not in message.message, "il traceback va nel log, non all'utente"
        assert process.wait(timeout=60) != 0
    finally:
        if process.poll() is None:
            _kill(process)
            process.wait()
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").rglob("*.wav"))


def _started(process: subprocess.Popen[str]) -> Path:
    message = _wait_for(
        _messages(process), (protocol.Started, protocol.Error), STARTED_TIMEOUT_S,
    )
    assert isinstance(message, protocol.Started), f"il worker non e' partito: {message!r}"
    return Path(message.out_dir)


def test_m4a_decodes_inside_the_package(frozen_exe: Path, tmp_path: Path):
    """Started arriva solo dopo la decodifica (pipeline.run_job): basta
    quello, senza scaricare un GB di pesi."""
    m4a = _make_m4a(frozen_exe, tmp_path)
    process = _start_job(frozen_exe, m4a, tmp_path / "out")
    try:
        out_dir = _started(process)
        assert out_dir.is_dir()
    finally:
        _kill(process)
        process.wait(timeout=30)


def test_kill_stops_worker_within_one_second(frozen_exe: Path, mix_44k: Path, tmp_path: Path):
    process = _start_job(frozen_exe, mix_44k, tmp_path / "out")
    try:
        out_dir = _started(process)
        started = time.monotonic()
        _kill(process)  # Annulla, come bridge.py (D2)
        process.wait(timeout=KILL_DEADLINE_S)
        assert time.monotonic() - started < KILL_DEADLINE_S
        # nessun file resta bloccato da un processo sopravvissuto
        shutil.rmtree(out_dir)
        assert not out_dir.exists()
    finally:
        if process.poll() is None:
            _kill(process)
            process.wait()
