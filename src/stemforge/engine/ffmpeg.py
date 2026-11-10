"""Il FFmpeg LGPL dell'app: trovarlo e usarlo come processo separato (D9).

BUILD_SPEC D9 e §5.7. Il binario si compila da packaging/ffmpeg/build.sh
e viaggia nel pacchetto: niente linking, quindi la conformità LGPL è
l'avviso con il link al sorgente. Non si cerca MAI nel PATH: un ffmpeg
GPL installato dall'utente non deve entrare nell'app, e il suo
comportamento non sarebbe quello collaudato.

Qui stanno le sole API di piattaforma di questo modulo (§10.4): nome
dell'eseguibile, profilo di build per lo sviluppo, CREATE_NO_WINDOW.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO

import numpy as np

log = logging.getLogger(__name__)

ENV_VAR = "STEMFORGE_FFMPEG"
# packaging/ffmpeg/out/<profilo>/ nei sorgenti: src/stemforge/engine -> repo
_DEV_OUT = Path(__file__).resolve().parents[3] / "packaging" / "ffmpeg" / "out"

PROBE_TIMEOUT_S = 30.0
# 30 minuti di 7.1 a 96 kHz si decodificano in decine di secondi anche sul
# Mac del 2012: oltre questo il processo è bloccato (disco di rete, FIFO)
DECODE_TIMEOUT_S = 300.0
ENCODE_TIMEOUT_S = 120.0
_READ_CHUNK = 1 << 20
_STDERR_TAIL = 600

FIXTURE_CODECS = frozenset({"aac", "alac", "flac", "pcm_s16le", "pcm_s24le"})

# Formati di campione con cui i negozi cifrano l'audio: FairPlay (iTunes
# .m4p: drms/drmi), CENC (enca), Audible (aavd). FFmpeg li vede ma non li
# decodifica, e senza questo controllo l'utente leggerebbe "file corrotto".
_DRM_RE = re.compile(r"\((?:drms|drmi|enca|aavd) /|encrypt|activation bytes", re.I)
_AUDIO_STREAM_RE = re.compile(r"Stream #\d+:\d+\S*: Audio:")
_DURATION_RE = re.compile(r"Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


class FfmpegMissing(RuntimeError):
    """Il FFmpeg dell'app non c'è: pacchetto incompleto o sviluppo senza build."""


class DecodeError(ValueError):
    """File che FFmpeg non sa leggere; il messaggio è per l'utente (§10.1)."""


def _exe_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _dev_profile() -> str:
    """Il profilo di build (§2.1) che corrisponde a questo interprete."""
    if sys.platform == "win32":
        return "win-x64"
    if sys.platform == "darwin":
        return "mac-arm64" if platform.machine() == "arm64" else "legacy-intel"
    return "linux-x64"


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _bundle_candidates() -> list[Path]:
    if not getattr(sys, "frozen", False):
        return []
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "ffmpeg" / _exe_name())
    exe_dir = Path(sys.executable).resolve().parent
    candidates += [exe_dir / _exe_name(), exe_dir / "ffmpeg" / _exe_name()]
    return candidates


def _env_candidate() -> Path | None:
    value = os.environ.get(ENV_VAR, "").strip()
    if not value:
        return None
    path = Path(value)
    return path / _exe_name() if path.is_dir() else path


def locate() -> Path | None:
    """Pacchetto, poi STEMFORGE_FFMPEG, poi la build di sviluppo. Mai il PATH."""
    for candidate in _bundle_candidates():
        if _is_executable(candidate):
            return candidate
    env = _env_candidate()
    if env is not None:
        if _is_executable(env):
            return env
        log.warning("%s=%s non è un eseguibile: ignorato", ENV_VAR, env)
    if not getattr(sys, "frozen", False):
        dev = _DEV_OUT / _dev_profile() / _exe_name()
        if _is_executable(dev):
            return dev
    return None


def _require() -> Path:
    found = locate()
    if found is None:
        raise FfmpegMissing(
            "Il decoder FFmpeg di StemForge non è stato trovato: reinstalla "
            f"l'app. (Sviluppo: packaging/ffmpeg/build.sh o {ENV_VAR}.)"
        )
    return found


def _popen_flags() -> int:
    # senza, ogni decodifica aprirebbe una console nera sopra l'app su Windows
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _file_arg(path: Path) -> str:
    # "file:" impedisce che un nome come "pipe:x" o "concat:a|b" diventi un
    # protocollo; il percorso assoluto toglie ogni dubbio sulla cartella
    return "file:" + str(Path(path).resolve())


def _drain(stream: IO[bytes], sink: bytearray) -> None:
    for chunk in iter(lambda: stream.read(_READ_CHUNK), b""):
        sink += chunk


def _run(
    args: list[str], timeout: float, stdin: bytes | None = None, quiet: bool = False
) -> tuple[int, bytearray, str]:
    """Esegue ffmpeg senza shell; stdout e stderr letti in parallelo.

    Due thread drenano le pipe (un file corrotto può scrivere migliaia di
    righe d'errore e, a pipe piena, ffmpeg si fermerebbe). L'uscita resta
    un bytearray: numpy la usa senza copiarla e l'array resta scrivibile.
    """
    verbosity = ["-loglevel", "error"] if quiet else []
    proc = subprocess.Popen(
        [str(_require()), "-hide_banner", "-nostdin", *verbosity, *args],
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_popen_flags(),
    )
    out, err = bytearray(), bytearray()
    readers = [threading.Thread(target=_drain, args=(s, b), daemon=True)
               for s, b in ((proc.stdout, out), (proc.stderr, err))]
    for reader in readers:
        reader.start()
    try:
        if stdin is not None:
            _feed(proc, stdin)
        code = proc.wait(timeout=timeout)
    except BaseException:
        # timeout, annulla (KeyboardInterrupt) o altro: senza kill i thread
        # di lettura aspetterebbero per sempre un ffmpeg ancora vivo
        proc.kill()
        proc.wait()
        raise
    finally:
        for reader in readers:
            reader.join()
    return code, out, err.decode("utf-8", errors="replace")


def _feed(proc: subprocess.Popen, data: bytes) -> None:
    assert proc.stdin is not None
    try:
        proc.stdin.write(data)
    except BrokenPipeError:  # ffmpeg è uscito prima: il codice d'uscita lo dice
        log.debug("ffmpeg ha chiuso stdin prima della fine dei dati")
    finally:
        proc.stdin.close()


def _tail(stderr: str) -> str:
    return stderr.strip()[-_STDERR_TAIL:]


def _user_error(path: Path, stderr: str) -> DecodeError:
    """Il messaggio giusto per l'utente a partire da ciò che dice ffmpeg."""
    name = Path(path).name
    if _DRM_RE.search(stderr):
        return DecodeError(
            f"{name} è protetto da DRM (per esempio un vecchio acquisto iTunes "
            ".m4p): StemForge non può leggerlo. Usa una copia senza protezione."
        )
    if "Stream #" in stderr and not _AUDIO_STREAM_RE.search(stderr):
        return DecodeError(f"{name} non contiene una traccia audio.")
    return DecodeError(
        f"{name} è danneggiato o non è un file audio: prova a riesportarlo "
        f"dal programma con cui l'hai creato. Dettaglio: {_tail(stderr)}"
    )


def _parse_wav_header(data: bytes) -> tuple[int, int] | None:
    """(canali, sample rate) dal chunk fmt di un WAV scritto da ffmpeg."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    pos = 12
    while pos + 8 <= len(data):
        tag, size = data[pos : pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if tag == b"fmt " and pos + 16 <= len(data):
            channels, rate = struct.unpack_from("<HI", data, pos + 10)
            return channels, rate
        pos += 8 + size + (size & 1)
    return None


def _stream_format(path: Path) -> tuple[int, int]:
    """Canali e sample rate esatti del primo flusso audio.

    Invece di interpretare la descrizione del layout ("5.1(side)",
    "hexagonal", "FL+FR+LFE"...) si fa scrivere a ffmpeg un solo frame in
    WAV e si leggono i due numeri dall'intestazione: sono gli stessi che
    ffmpeg userà decodificando.
    """
    args = ["-i", _file_arg(path), "-map", "0:a:0", "-frames:a", "1",
            "-c:a", "pcm_f32le", "-f", "wav", "pipe:1"]
    try:
        code, out, err = _run(args, PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise DecodeError(f"{Path(path).name}: lettura bloccata, riprova.") from exc
    header = _parse_wav_header(bytes(out[:4096])) if code == 0 else None
    if header is None or header[0] == 0 or header[1] == 0:
        if code == 0:
            raise DecodeError(f"{Path(path).name} non contiene campioni audio.")
        raise _user_error(path, err)
    return header


def decode(path: Path) -> tuple[np.ndarray, int]:
    """Tutto il primo flusso audio come float32 [frames, channels].

    Sample rate e canali sono quelli del file (il downmix e il resampling
    sono compito di audio_io). Nessun file temporaneo: i campioni arrivano
    da una pipe in f32le grezzo, con canali e sample rate fissati a quelli
    letti prima, così la forma dell'array non dipende da cosa c'è nel flusso.
    """
    _require()  # un'app senza decoder è un guasto dell'app, non del file
    if not Path(path).is_file():
        raise DecodeError(f"{Path(path).name} non esiste o non è un file.")
    channels, samplerate = _stream_format(path)
    args =["-i", _file_arg(path), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-ac", str(channels), "-ar", str(samplerate),
            "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    try:
        code, out, err = _run(args, DECODE_TIMEOUT_S, quiet=True)
    except subprocess.TimeoutExpired as exc:
        raise DecodeError(
            f"La decodifica di {Path(path).name} non è finita entro "
            f"{DECODE_TIMEOUT_S:.0f} s: il file è su un disco lento o bloccato?"
        ) from exc
    if code != 0:
        raise _user_error(path, err)
    frame_bytes = 4 * channels
    usable = len(out) - len(out) % frame_bytes
    if usable == 0:
        raise DecodeError(f"{Path(path).name} non contiene campioni audio.")
    del out[usable:]
    audio = np.frombuffer(out, dtype="<f4").reshape(-1, channels)
    return audio.astype(np.float32, copy=False), samplerate


def probe_duration(path: Path) -> float | None:
    """Durata in secondi dall'intestazione, o None se non è un file audio."""
    try:
        _, _, err = _run(["-i", _file_arg(path)], PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.warning("probe di %s oltre %s s", Path(path).name, PROBE_TIMEOUT_S)
        return None
    # senza output ffmpeg esce con errore anche quando il file è buono:
    # conta solo che ci sia un flusso audio e una durata
    match = _DURATION_RE.search(err)
    if match is None or not _AUDIO_STREAM_RE.search(err):
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


_WAVE_FORMAT_IEEE_FLOAT = 3
_FLOAT_BYTES = 4


def _float_wav(interleaved: np.ndarray, samplerate: int) -> bytes:
    """WAV IEEE float da [frames, channels] float32 little-endian."""
    channels = interleaved.shape[1]
    data = interleaved.tobytes()
    block = channels * _FLOAT_BYTES
    fmt = struct.pack("<HHIIHH", _WAVE_FORMAT_IEEE_FLOAT, channels, samplerate,
                      samplerate * block, block, 8 * _FLOAT_BYTES)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def encode_fixture(audio: np.ndarray, samplerate: int, dest: Path, codec: str) -> Path:
    """Scrive [channels, frames] float32 con un codec dei test (aac, alac...).

    Il contenitore lo sceglie ffmpeg dall'estensione di dest (.m4a, .caf,
    .flac, .wav, .mp4). Serve ai test e al selftest: i fixture si generano
    in codice, mai materiale protetto (§10.6).
    """
    if codec not in FIXTURE_CODECS:
        raise ValueError(f"codec {codec!r} non tra {sorted(FIXTURE_CODECS)}")
    if audio.ndim != 2 or audio.shape[0] == 0 or audio.shape[1] == 0:
        raise ValueError(f"atteso [channels, frames], ricevuto {audio.shape}")
    # in ingresso un WAV float completo invece di f32le grezzo: il demuxer
    # wav c'è già nella build minima, quello f32le no (D9, solo il necessario)
    wav = _float_wav(np.ascontiguousarray(audio.T, dtype="<f4"), samplerate)
    args = ["-f", "wav", "-i", "pipe:0", "-c:a", codec, "-y", _file_arg(dest)]
    code, _, err = _run(args, ENCODE_TIMEOUT_S, stdin=wav, quiet=True)
    if code != 0:
        raise RuntimeError(f"ffmpeg non ha scritto {Path(dest).name}: {_tail(err)}")
    return Path(dest)


def license_info() -> str:
    """Versione, configurazione e licenza del FFmpeg in uso (selftest, notices)."""
    _, version, _ = _run(["-version"], PROBE_TIMEOUT_S)
    _, license_text, _ = _run(["-L"], PROBE_TIMEOUT_S)
    lines = version.decode("utf-8", errors="replace").splitlines()
    head = [line for line in lines if line.startswith(("ffmpeg version", "configuration:"))]
    text = " ".join(license_text.decode("utf-8", errors="replace").split())
    if "GNU General Public License" in text:
        verdict = "license: GPL (NON conforme a D9)"
    elif "GNU Lesser General Public License" in text and "version 2.1" in text:
        verdict = "license: LGPL version 2.1 or later"
    else:
        verdict = "license: sconosciuta (NON conforme a D9)"
    return "\n".join([*head, verdict, f"path: {locate()}"])
