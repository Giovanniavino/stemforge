"""Collaudo dell'app installata: `StemForge --selftest` (BUILD_SPEC §10.5).

Nasce dai guasti visti sul campo, che i test sui sorgenti non potevano
vedere perché esistono solo DENTRO il pacchetto: file dati di demucs non
inclusi, certificati HTTPS assenti, worker che muore al lancio. Gira
sull'app impacchettata in CI, su ogni piattaforma, prima che un file
venga pubblicato; sulla macchina dell'utente serve come diagnostica.

Esito: report JSON (--report) + righe leggibili + codice di uscita.
"""

from __future__ import annotations

import json
import os
import platform
import ssl
import subprocess
import sys
import tempfile
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from stemforge import __version__
from stemforge.engine.device import prepare_runtime_env
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind
from stemforge.worker import protocol
from stemforge.worker.launch import worker_command

_SAMPLERATE = 44100
_DECODE_SECONDS = 2.0
_DECODE_FORMATS = ("wav", "flac", "ogg", "mp3", "m4a")
# mp3/m4a aggiungono il ritardo del codec: decine di ms, mai 100
_DURATION_TOLERANCE_S = 0.1
_ROUNDTRIP_SECONDS = 6.0
_ROUNDTRIP_TIMEOUT_S = 45 * 60  # include il download dei pesi su rete lenta
_MAX_RESIDUAL_DBFS = -40.0  # invariante di ricostruzione (§10.2)
_WEIGHTS_HOST = "https://dl.fbaipublicfiles.com/demucs/"

ExtraCheck = tuple[str, Callable[[], str]]


class _Skip(Exception):
    """Controllo non eseguibile qui (es. senza rete): né ok né guasto."""


@dataclass
class Check:
    name: str
    status: str  # "ok" | "fail" | "skip"
    detail: str = ""


def _run_check(name: str, check: Callable[[], str]) -> Check:
    try:
        return Check(name, "ok", check() or "")
    except _Skip as exc:
        return Check(name, "skip", str(exc))
    except Exception:  # un controllo che fallisce non ferma gli altri
        return Check(name, "fail", traceback.format_exc(limit=10))


def _tone(seconds: float, noise: bool = False) -> np.ndarray:
    """[2, campioni] float32: due sinusoidi (+ rumore), deterministico."""
    t = np.arange(int(seconds * _SAMPLERATE)) / _SAMPLERATE
    left = 0.4 * np.sin(2 * np.pi * 220.0 * t) + 0.2 * np.sin(2 * np.pi * 1760.0 * t)
    if noise:
        left = left + 0.05 * np.random.default_rng(seed=7).standard_normal(t.size)
    right = np.roll(left, 11) * 0.95
    return np.stack([left, right]).astype(np.float32)


# -- controlli ------------------------------------------------------------


def _check_runtime() -> str:
    import torch

    return (
        f"StemForge {__version__} · Python {platform.python_version()} · "
        f"{platform.system()} {platform.release()} {platform.machine()} · "
        f"torch {torch.__version__} · pacchetto={bool(getattr(sys, 'frozen', False))}"
    )


def _check_demucs_data() -> str:
    from demucs import pretrained

    root = Path(pretrained.REMOTE_ROOT)
    index = root / "files.txt"
    if not index.is_file():
        raise FileNotFoundError(f"indice dei modelli assente: {index}")
    configs = sorted(p.stem for p in root.glob("*.yaml"))
    for needed in ("htdemucs_ft", "htdemucs_6s"):
        if needed not in configs:
            raise FileNotFoundError(f"configurazione {needed}.yaml assente in {root}")
    return f"files.txt + {len(configs)} configurazioni"


def _check_tls(network: bool) -> str:
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile or not Path(cafile).is_file():
        raise FileNotFoundError(f"bundle dei certificati assente: {cafile!r}")
    context = ssl.create_default_context(cafile=cafile)
    if not network:
        raise _Skip("certificati caricati; connessione non provata (--offline)")
    request = urllib.request.Request(_WEIGHTS_HOST, method="HEAD")
    try:
        urllib.request.urlopen(request, timeout=30, context=context).close()
    except urllib.error.HTTPError:
        pass  # il server ha risposto: la stretta di mano TLS è riuscita
    return "connessione HTTPS al server dei modelli riuscita"


def _write_aac(path: Path, audio: np.ndarray) -> None:
    import av

    with av.open(str(path), "w", format="mp4") as container:
        stream = container.add_stream("aac", rate=_SAMPLERATE)
        frame = av.AudioFrame.from_ndarray(audio, format="fltp", layout="stereo")
        frame.sample_rate = _SAMPLERATE
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)


def _write_encoded(path: Path, fmt: str, audio: np.ndarray) -> None:
    if fmt == "m4a":
        _write_aac(path, audio)
        return
    import soundfile as sf

    subtype = {"wav": "PCM_24", "flac": "PCM_24", "ogg": "VORBIS", "mp3": "MPEG_LAYER_III"}
    sf.write(str(path), audio.T, _SAMPLERATE, subtype=subtype[fmt])


def _check_decoders(tmp: Path) -> str:
    from stemforge.engine import audio_io

    audio = _tone(_DECODE_SECONDS)
    for fmt in _DECODE_FORMATS:
        path = tmp / f"decode.{fmt}"
        _write_encoded(path, fmt, audio)
        loaded = audio_io.load(path)
        if abs(loaded.duration_s - _DECODE_SECONDS) > _DURATION_TOLERANCE_S:
            raise AssertionError(f"{fmt}: durata {loaded.duration_s:.3f} s invece di {_DECODE_SECONDS} s")
        if float(np.max(np.abs(loaded.data))) < 0.05:
            raise AssertionError(f"{fmt}: decodificato in silenzio")
        if audio_io.probe_duration(path) is None:
            raise AssertionError(f"{fmt}: durata non leggibile senza decodificare")
    return "letti: " + ", ".join(_DECODE_FORMATS)


def _run_worker(job: SeparationJob) -> tuple[list[protocol.Message], str]:
    """Lancia il worker come lo lancia l'app (stesso comando, stesso protocollo)."""
    proc = subprocess.run(
        worker_command(),
        input=job.to_json() + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_ROUNDTRIP_TIMEOUT_S,
    )
    messages = [m for m in map(protocol.decode, proc.stdout.splitlines()) if m is not None]
    return messages, f"exit {proc.returncode}\n{proc.stderr[-4000:]}"


def _verify_stems(out_dir: Path, source: Path) -> str:
    import soundfile as sf

    mix, rate = sf.read(str(source), dtype="float32", always_2d=True)
    total = np.zeros_like(mix)
    for name in ("vocals.wav", "other.wav"):
        data, stem_rate = sf.read(str(out_dir / name), dtype="float32", always_2d=True)
        if stem_rate != rate:
            raise AssertionError(f"{name}: {stem_rate} Hz invece di {rate} Hz")
        if data.shape != mix.shape:
            raise AssertionError(f"{name}: forma {data.shape} invece di {mix.shape}")
        total += data
    if not (out_dir / "manifest.json").is_file():
        raise AssertionError("manifest.json non scritto")
    residual = float(np.sqrt(np.mean((total - mix) ** 2)))
    residual_db = 20.0 * np.log10(max(residual, 1e-12))
    if residual_db > _MAX_RESIDUAL_DBFS:
        raise AssertionError(f"somma degli stem lontana dal mix: {residual_db:.1f} dBFS")
    return f"stem allineati al campione, residuo di ricostruzione {residual_db:.1f} dBFS"


def _check_worker_roundtrip(tmp: Path, network: bool) -> str:
    if not network:
        raise _Skip("serve la rete per scaricare i modelli (--offline)")
    import soundfile as sf

    source = tmp / "selftest.wav"
    sf.write(str(source), _tone(_ROUNDTRIP_SECONDS, noise=True).T, _SAMPLERATE, subtype="PCM_24")
    job = SeparationJob(
        source=source,
        wanted=(StemKind.VOCALS, StemKind.OTHER),
        quality="fast",
        out_dir=tmp / "out",
        device="auto",
    )
    messages, diagnostics = _run_worker(job)
    errors = [m for m in messages if isinstance(m, protocol.Error)]
    if errors:
        raise RuntimeError(f"il worker ha segnalato: {errors[0].message}\n{errors[0].detail}")
    done = [m for m in messages if isinstance(m, protocol.Done)]
    if not done:
        raise RuntimeError(f"il worker è terminato senza risultato:\n{diagnostics}")
    return _verify_stems(Path(done[0].out_dir), source)


# -- orchestrazione ---------------------------------------------------------


def _print_report(checks: list[Check], ok: bool) -> None:
    if sys.stdout is None:  # app a finestra senza console: basta il report
        return
    if hasattr(sys.stdout, "reconfigure"):
        # una console cp1252 non deve far crollare il collaudo su un accento
        sys.stdout.reconfigure(errors="replace")
    for check in checks:
        print(f"[{check.status:>4}] {check.name}: {check.detail.strip()}", flush=True)
    print("COLLAUDO RIUSCITO" if ok else "COLLAUDO FALLITO", flush=True)


def run(
    report_path: Path | None,
    network: bool = True,
    extra: Iterable[ExtraCheck] = (),
) -> int:
    prepare_runtime_env()
    with tempfile.TemporaryDirectory(prefix="stemforge-selftest-", ignore_cleanup_errors=True) as name:
        tmp = Path(name)
        # calibrazione e verdetto MPS del collaudo non sporcano quelli veri
        os.environ.setdefault("STEMFORGE_CALIBRATION", str(tmp / "calibration.json"))
        checks = [
            _run_check("ambiente", _check_runtime),
            _run_check("dati di demucs nel pacchetto", _check_demucs_data),
            _run_check("certificati HTTPS", lambda: _check_tls(network)),
            _run_check("decodifica dei formati", lambda: _check_decoders(tmp)),
            *(_run_check(label, check) for label, check in extra),
            _run_check("separazione reale nel processo worker", lambda: _check_worker_roundtrip(tmp, network)),
        ]
    ok = all(check.status != "fail" for check in checks)
    if report_path is not None:
        report = {"version": __version__, "ok": ok, "checks": [asdict(c) for c in checks]}
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_report(checks, ok)
    return 0 if ok else 1
