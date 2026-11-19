"""Spazio su disco: la stima PRIMA di iniziare e il disco che si riempie
durante la scrittura (BUILD_SPEC §10.1).

La stima viene dal piano (file scritti × durata × byterate degli stem,
+20%): qui si verifica contro i file VERI che la pipeline scrive, per
multicanale ridotto a stereo, mono, de-riverbero (vocals_wet in più),
WAV e FLAC, con rumore bianco che FLAC non sa comprimere (caso peggiore).
"""

from __future__ import annotations

import errno
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from stemforge.engine import audio_io
from stemforge.engine.errors import InsufficientDiskError
from stemforge.export import folder
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K
from stemforge.worker import preflight
from stemforge.worker.i18n import t
from stemforge.worker.messages import user_message
from stemforge.worker.pipeline import run_job

from tests.integration.conftest import FakeDemucs, collect_messages

SECONDS = 3.0
MARGIN = 1.2  # §10.1
PCM24_BYTES = 3


class FakeDereverb:
    """De-riverbero finto: toglie il 30% della voce, come farebbe il vero."""

    name = "dereverb"
    samplerate = 44100
    provides = frozenset({K.VOCALS})

    def separate(self, audio, wanted, on_progress, should_cancel):
        on_progress(1.0)
        return {K.VOCALS: audio * 0.7}


def _noise_file(path: Path, samplerate: int, channels: int) -> Path:
    rng = np.random.default_rng(seed=3)
    data = (rng.standard_normal((int(SECONDS * samplerate), channels)) * 0.2).astype(np.float32)
    sf.write(str(path), data, samplerate, subtype="PCM_24")
    return path


def _job(source: Path, out: Path, wanted: tuple[K, ...], fmt: str = "wav",
         dereverb: bool = False) -> SeparationJob:
    return SeparationJob(source=source, wanted=wanted, quality="balanced", out_dir=out,
                         fmt=fmt, device="cpu", dereverb_vocals=dereverb)


def _backends() -> dict:
    fake = FakeDemucs()
    return {
        ("demucs4", "htdemucs_ft", "cpu", "balanced"): fake,
        ("dereverb", "dereverb", "cpu", "balanced"): FakeDereverb(),
    }


def _audio_bytes(out_dir: Path, fmt: str) -> int:
    return sum(p.stat().st_size for p in out_dir.glob(f"*.{fmt}"))


@pytest.mark.parametrize("channels, stem_channels", [(1, 1), (2, 2), (6, 2), (8, 2)])
def test_estimate_counts_the_channels_of_the_stems_not_of_the_file(channels, stem_channels, tmp_path):
    # un 5.1 o un 7.1 escono stereo (§5.7 regola 7): stimarli a 6-8
    # canali rifiuterebbe per niente un disco che basta
    source = audio_io.load(_noise_file(tmp_path / "f.wav", 48000, channels))
    job = _job(tmp_path / "f.wav", tmp_path / "out", (K.VOCALS, K.OTHER))
    expected = 2 * SECONDS * 48000 * stem_channels * PCM24_BYTES * MARGIN
    assert preflight.needed_bytes(job, source) == pytest.approx(expected, rel=1e-6)


def test_dereverb_counts_vocals_wet(tmp_path):
    source = audio_io.load(_noise_file(tmp_path / "f.wav", 44100, 2))
    plain = _job(tmp_path / "f.wav", tmp_path / "out", (K.VOCALS, K.OTHER))
    wet = _job(tmp_path / "f.wav", tmp_path / "out", (K.VOCALS, K.OTHER), dereverb=True)
    assert preflight.files_written(plain) == 2
    assert preflight.files_written(wet) == 3
    assert preflight.needed_bytes(wet, source) == pytest.approx(
        preflight.needed_bytes(plain, source) * 3 / 2, rel=1e-6
    )


@pytest.mark.parametrize("fmt", ["wav", "flac"])
@pytest.mark.parametrize("channels, samplerate", [(6, 48000), (1, 22050), (2, 44100)])
def test_real_output_fits_the_estimate(fmt, channels, samplerate, tmp_path):
    path = _noise_file(tmp_path / "noise.wav", samplerate, channels)
    job = _job(path, tmp_path / "out", (K.VOCALS, K.DRUMS, K.OTHER), fmt=fmt, dereverb=True)
    needed = preflight.needed_bytes(job, audio_io.load(path))
    result = run_job(job, lambda m: None, backends=_backends())

    names = sorted(p.name for p in result.out_dir.glob(f"*.{fmt}"))
    assert names == sorted(f"{n}.{fmt}" for n in ("vocals", "drums", "other", "vocals_wet"))
    written = _audio_bytes(result.out_dir, fmt)
    assert written <= needed, f"stima {needed} B, scritti {written} B"
    # e non è un fattore fisso: resta entro il margine dichiarato dal PCM vero
    stem_channels = 1 if channels == 1 else 2
    pcm = len(names) * int(SECONDS * samplerate) * stem_channels * PCM24_BYTES
    assert needed <= pcm * MARGIN * 1.001


def test_precheck_refuses_before_creating_anything(tmp_path, monkeypatch):
    path = _noise_file(tmp_path / "f.wav", 44100, 2)
    job = _job(path, tmp_path / "out", (K.VOCALS, K.OTHER))
    needed = preflight.needed_bytes(job, audio_io.load(path))
    monkeypatch.setattr(preflight, "free_bytes", lambda target: needed - 1)
    messages, emit = collect_messages()
    with pytest.raises(InsufficientDiskError) as info:
        run_job(job, emit, backends=_backends())
    assert not (tmp_path / "out").exists(), "nessuna cartella prima del controllo"
    assert not messages, "nessun Started: il job non è mai partito"
    assert info.value.params["folder"] == str(tmp_path / "out")

    monkeypatch.setattr(preflight, "free_bytes", lambda target: needed)
    assert run_job(job, emit, backends=_backends()).out_dir.is_dir()


def test_free_bytes_walks_up_to_an_existing_folder(tmp_path):
    missing = tmp_path / "non" / "ancora" / "creata"
    assert preflight.free_bytes(missing) > 0


@pytest.mark.parametrize("lang, hints", [("it", ("Libera spazio", "MB")),
                                         ("en", ("Free up space", "MB"))])
def test_precheck_message_says_how_much_and_what_to_do(lang, hints, tmp_path, monkeypatch):
    monkeypatch.setenv("STEMFORGE_LOCALE", lang)
    path = _noise_file(tmp_path / "f.wav", 44100, 2)
    job = _job(path, tmp_path / "out", (K.VOCALS, K.OTHER))
    source = audio_io.load(path)
    with pytest.raises(InsufficientDiskError) as info:
        preflight.check_disk(job, source, free=lambda target: 1_000_000)
    text = user_message(info.value)
    needed_mb = -(-preflight.needed_bytes(job, source) // 1_000_000)
    assert needed_mb == 2  # 1.9 MB arrotondati per eccesso, mai "0 MB"
    assert f"{needed_mb} MB" in text and "1 MB" in text
    assert str(tmp_path / "out") in text
    assert all(h in text for h in hints)


def test_disk_filling_up_while_writing_becomes_disk_full(tmp_path, monkeypatch):
    # libsndfile dice solo "errore di scrittura": se sul volume non c'è
    # più posto per lo stem, la causa è il disco pieno (§10.1)
    def failing_write(*args, **kwargs):
        raise RuntimeError("Error : unspecified internal error")

    monkeypatch.setattr(folder, "sf", SimpleNamespace(write=failing_write))
    monkeypatch.setattr(folder, "shutil", SimpleNamespace(disk_usage=lambda p: SimpleNamespace(free=10)))
    audio = np.zeros((2, 44100), dtype=np.float32)
    with pytest.raises(OSError) as info:
        folder.write_stem(tmp_path, K.VOCALS, audio, 44100, "wav")
    assert info.value.errno == errno.ENOSPC
    assert user_message(info.value) == t("err.disk_full")


def test_a_write_error_with_space_left_is_not_disk_full(tmp_path, monkeypatch):
    def failing_write(*args, **kwargs):
        raise RuntimeError("Error : unspecified internal error")

    monkeypatch.setattr(folder, "sf", SimpleNamespace(write=failing_write))
    with pytest.raises(RuntimeError):
        folder.write_stem(tmp_path, K.VOCALS, np.zeros((2, 100), np.float32), 44100, "wav")
