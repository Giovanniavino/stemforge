"""Pipeline completa con backend finto: l'invariante di ricostruzione
(§10.2) e i comportamenti di §5.2.4, senza modelli reali."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from stemforge.model.job import SeparationJob
from stemforge.model.manifest import Manifest
from stemforge.model.stem import StemKind as K
from stemforge.worker import protocol
from stemforge.worker.runner import run_job

RECONSTRUCTION_LIMIT_DBFS = -40.0


def make_job(source: Path, out: Path, *wanted: K, quality: str = "balanced",
             fmt: str = "wav", dereverb: bool = False) -> SeparationJob:
    return SeparationJob(
        source=source, wanted=tuple(wanted), quality=quality,
        out_dir=out, fmt=fmt, device="cpu", dereverb_vocals=dereverb,
    )


def reconstruction_rms_dbfs(out_dir: Path, source: Path, fmt: str = "wav") -> float:
    mix, sr_mix = sf.read(source, dtype="float64", always_2d=True)
    total = np.zeros_like(mix)
    for stem in sorted(out_dir.glob(f"*.{fmt}")):
        if stem.stem == "vocals_wet":
            continue
        data, sr = sf.read(stem, dtype="float64", always_2d=True)
        assert sr == sr_mix, f"{stem.name}: sample rate diverso"
        assert data.shape == mix.shape, f"{stem.name}: lunghezza/canali diversi"
        total += data
    residual = total - mix
    rms = float(np.sqrt(np.mean(np.square(residual))))
    return -120.0 if rms == 0 else 20.0 * math.log10(rms)


def test_four_stems_reconstruct_the_mix(mix_44k, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    out_base = tmp_path / "out"
    result = run_job(
        make_job(mix_44k, out_base, K.VOCALS, K.DRUMS, K.BASS, K.OTHER),
        emit=lambda m: None, backends=cache,
    )
    names = {s.file for s in result.stems}
    assert names == {"vocals.wav", "drums.wav", "bass.wav", "other.wav"}
    assert reconstruction_rms_dbfs(result.out_dir, mix_44k) < RECONSTRUCTION_LIMIT_DBFS
    manifest = Manifest.from_json((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.audio.samplerate == 44100
    assert manifest.audio.bit_depth == 24
    assert manifest.engine.model == "htdemucs_ft"


def test_48k_source_reconstructs_at_48k(mix_48k, tmp_path, fake_backends):
    # round-trip di resampling: lunghezza esatta e invariante al sr originale
    cache, _fake = fake_backends()
    result = run_job(
        make_job(mix_48k, tmp_path / "out", K.VOCALS, K.DRUMS, K.BASS, K.OTHER),
        emit=lambda m: None, backends=cache,
    )
    info = sf.info(str(result.out_dir / "vocals.wav"))
    source_info = sf.info(str(mix_48k))
    assert info.samplerate == 48000
    assert info.frames == source_info.frames
    assert reconstruction_rms_dbfs(result.out_dir, mix_48k) < RECONSTRUCTION_LIMIT_DBFS


def test_mono_source_stays_mono(mix_mono, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    result = run_job(
        make_job(mix_mono, tmp_path / "out", K.VOCALS, K.OTHER),
        emit=lambda m: None, backends=cache,
    )
    info = sf.info(str(result.out_dir / "vocals.wav"))
    assert info.channels == 1
    assert reconstruction_rms_dbfs(result.out_dir, mix_mono) < RECONSTRUCTION_LIMIT_DBFS


def test_instrumental_is_mix_minus_vocals(mix_44k, tmp_path, fake_backends):
    cache, fake = fake_backends()
    result = run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, K.INSTRUMENTAL),
        emit=lambda m: None, backends=cache,
    )
    # una sola inferenza, sul solo sotto-modello vocals (§5.1.1)
    assert fake.calls == [frozenset({K.VOCALS})]
    assert reconstruction_rms_dbfs(result.out_dir, mix_44k) < RECONSTRUCTION_LIMIT_DBFS


def test_best_runs_full_ensemble(mix_44k, tmp_path, fake_backends):
    cache, fake = fake_backends(quality="best")
    run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, quality="best"),
        emit=lambda m: None, backends=cache,
    )
    assert fake.calls == [frozenset({K.VOCALS, K.DRUMS, K.BASS, K.OTHER})]


def test_derived_unavailable_falls_back_to_base(mix_44k, tmp_path, fake_backends):
    # §5.2.4: si ottiene drums.wav invece di kick, con avviso non bloccante
    cache, _fake = fake_backends()
    messages, emit = [], None

    def emit(m):
        messages.append(m)

    result = run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, K.KICK),
        emit=emit, backends=cache,
    )
    names = {s.file for s in result.stems}
    assert names == {"vocals.wav", "drums.wav"}
    assert not (result.out_dir / "kick.wav").exists()
    assert any(isinstance(m, protocol.Warning_) for m in messages)
    assert result.warnings


def test_dereverb_unavailable_keeps_vocals(mix_44k, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    result = run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, dereverb=True),
        emit=lambda m: None, backends=cache,
    )
    assert (result.out_dir / "vocals.wav").exists()
    assert not (result.out_dir / "vocals_wet.wav").exists()
    assert result.warnings
    manifest = Manifest.from_json((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.dereverb is False


def test_silent_stem_warns(mix_44k, tmp_path, fake_backends):
    coeffs = {K.VOCALS: 0.0, K.DRUMS: 0.2, K.BASS: 0.1, K.OTHER: 0.3}
    cache, _fake = fake_backends(coeffs=coeffs)
    result = run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, K.DRUMS),
        emit=lambda m: None, backends=cache,
    )
    assert any("quasi silenzioso" in w for w in result.warnings)


def test_flac_output(mix_44k, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    result = run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, K.OTHER, fmt="flac"),
        emit=lambda m: None, backends=cache,
    )
    assert {s.file for s in result.stems} == {"vocals.flac", "other.flac"}
    assert reconstruction_rms_dbfs(result.out_dir, mix_44k, fmt="flac") < RECONSTRUCTION_LIMIT_DBFS


def test_progress_monotonic_and_started_first(mix_44k, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    messages: list = []
    run_job(
        make_job(mix_44k, tmp_path / "out", K.VOCALS, K.DRUMS, K.OTHER),
        emit=messages.append, backends=cache,
    )
    assert isinstance(messages[0], protocol.Started)
    values = [m.value for m in messages if isinstance(m, protocol.Progress)]
    assert values == sorted(values), "il progresso non torna mai indietro (§5.5)"
    assert values[-1] >= 0.999
    assert any(isinstance(m, protocol.Done) for m in messages)


def test_collision_never_overwrites(mix_44k, tmp_path, fake_backends):
    cache, _fake = fake_backends()
    out = tmp_path / "out"
    first = run_job(make_job(mix_44k, out, K.VOCALS, K.OTHER),
                    emit=lambda m: None, backends=cache)
    second = run_job(make_job(mix_44k, out, K.VOCALS, K.OTHER),
                     emit=lambda m: None, backends=cache)
    assert first.out_dir.name == "brano"
    assert second.out_dir.name == "brano (2)"
