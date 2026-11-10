"""Decodifica dei file audio: soundfile, poi il FFmpeg LGPL dell'app.

BUILD_SPEC §5.7 regola 1, D9, §10.1. soundfile (libsndfile) legge
wav/flac/ogg/aiff/mp3; tutto il resto (m4a/aac, alac) passa dal FFmpeg
compilato da noi, chiamato come processo separato da engine/ffmpeg.py.
Mai un ffmpeg installato dall'utente e mai PyAV: il suo FFmpeg è GPLv3.

Ogni guasto diventa un UnsupportedFormatError con la chiave del
messaggio giusto (corrotto, DRM, formato sconosciuto, decoder assente):
il worker lo traduce, l'utente legge cosa fare, il log ha il dettaglio.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from types import ModuleType

import numpy as np
import soundfile as sf

from stemforge.engine.errors import UnsupportedFormatError

log = logging.getLogger(__name__)

# Letti da libsndfile: se soundfile fallisce su questi, il file è rotto.
SOUNDFILE_EXTENSIONS = frozenset(
    {".wav", ".wave", ".flac", ".ogg", ".oga", ".mp3", ".aiff", ".aif", ".aifc"}
)
# Solo FFmpeg: m4a porta AAC o ALAC, .aac è AAC grezzo (ADTS).
FFMPEG_EXTENSIONS = frozenset({".m4a", ".aac"})
SUPPORTED_EXTENSIONS = SOUNDFILE_EXTENSIONS | FFMPEG_EXTENSIONS

_FFMPEG_MODULE = "stemforge.engine.ffmpeg"


def ffmpeg_module() -> ModuleType | None:
    """Il modulo che guida il FFmpeg dell'app, o None se manca.

    importlib invece di `from stemforge.engine import ffmpeg`: passa da
    sys.modules, dove i test mettono un FFmpeg finto.
    """
    try:
        return importlib.import_module(_FFMPEG_MODULE)
    except ImportError:
        log.warning("%s non importabile: niente m4a/aac/alac", _FFMPEG_MODULE, exc_info=True)
        return None


def _missing_decoder(path: Path, detail: str) -> UnsupportedFormatError:
    suffix = path.suffix.lower()
    if suffix in SOUNDFILE_EXTENSIONS:
        # soundfile doveva leggerlo da solo: è il file a essere rotto
        return UnsupportedFormatError("err.corrupt", detail, name=path.name)
    if suffix in FFMPEG_EXTENSIONS:
        return UnsupportedFormatError("err.ffmpeg_missing", detail, name=path.name)
    return UnsupportedFormatError("err.unsupported", detail, name=path.name)


def _is_drm(exc: Exception) -> bool:
    # `reason` se engine/ffmpeg.py la espone; "DRM" è uguale in ogni lingua
    return getattr(exc, "reason", None) == "drm" or "DRM" in str(exc)


def _decode_failure(path: Path, exc: Exception, detail: str) -> UnsupportedFormatError:
    if _is_drm(exc):
        return UnsupportedFormatError("err.drm", detail, name=path.name)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return UnsupportedFormatError("err.unsupported", detail, name=path.name)
    return UnsupportedFormatError("err.corrupt", detail, name=path.name)


def _read_with_ffmpeg(path: Path, sf_error: Exception) -> tuple[np.ndarray, int]:
    ffmpeg = ffmpeg_module()
    if ffmpeg is None:
        raise _missing_decoder(path, f"soundfile: {sf_error}; ffmpeg: modulo assente")
    try:
        data, samplerate = ffmpeg.decode(path)
    except ffmpeg.FfmpegMissing as exc:
        raise _missing_decoder(path, f"soundfile: {sf_error}; ffmpeg: {exc}") from exc
    except ffmpeg.DecodeError as exc:
        raise _decode_failure(path, exc, f"soundfile: {sf_error}; ffmpeg: {exc}") from exc
    return np.asarray(data, dtype=np.float32), int(samplerate)


def read(path: Path) -> tuple[np.ndarray, int]:
    """Tutto il file come [frames, channels] float32, al sample rate
    originale e con TUTTI i canali: downmix e resampling sono di audio_io."""
    path = Path(path)
    if not path.is_file():
        raise UnsupportedFormatError("err.not_found", str(path), name=path.name)
    try:
        data, samplerate = sf.read(str(path), dtype="float32", always_2d=True)
    except RuntimeError as exc:  # LibsndfileError: non è un formato di libsndfile
        return _read_with_ffmpeg(path, exc)
    return data, int(samplerate)


def soundfile_duration(path: Path) -> float | None:
    """Durata dall'intestazione, se libsndfile sa leggerla; senza decodificare."""
    try:
        info = sf.info(str(path))
    except RuntimeError:  # non è un formato di libsndfile: decide FFmpeg
        return None
    return info.frames / info.samplerate if info.samplerate > 0 else None


def probe_duration(path: Path) -> float | None:
    """Durata in secondi senza decodificare, o None se il file non si legge."""
    path = Path(path)
    seconds = soundfile_duration(path)
    if seconds is not None:
        return seconds
    ffmpeg = ffmpeg_module()
    if ffmpeg is None:
        return None
    try:
        return ffmpeg.probe_duration(path)
    except (ffmpeg.FfmpegMissing, ffmpeg.DecodeError, OSError) as exc:
        log.info("durata di %s non leggibile: %s", path.name, exc)
        return None
