"""Test esaustivi del pianificatore: il test unitario più importante
del progetto (BUILD_SPEC §10.3). Gira senza torch, in millisecondi."""

from __future__ import annotations

from pathlib import Path

import pytest

from stemforge.engine.planner import (
    DEFAULT_RATES,
    estimate_seconds,
    plan,
    subtraction_terms,
)
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K


def make_job(*wanted: K, quality: str = "balanced", dereverb: bool = False) -> SeparationJob:
    return SeparationJob(
        source=Path("brano.wav"),
        wanted=tuple(wanted),
        quality=quality,
        out_dir=Path("out"),
        dereverb_vocals=dereverb,
    )


def backends_of(plan_) -> list[str]:
    return [p.backend for p in plan_.passes]


# --- primo stadio: scelta modello e §5.1.1 -------------------------------


def test_single_vocals_balanced_is_one_submodel():
    p = plan(make_job(K.VOCALS))
    assert p.first_stage_model == "htdemucs_ft"
    first = p.passes[0]
    assert first.mode == "partial"
    assert first.needed == (K.VOCALS,)
    assert first.units == 1.0
    assert len(p.passes) == 1


def test_single_vocals_best_runs_full_ensemble():
    p = plan(make_job(K.VOCALS, quality="best"))
    first = p.passes[0]
    assert first.mode == "full"
    assert first.units == 4.0


def test_two_stems_partial():
    p = plan(make_job(K.VOCALS, K.DRUMS))
    first = p.passes[0]
    assert first.mode == "partial"
    assert set(first.needed) == {K.DRUMS, K.VOCALS}
    assert first.units == 2.0


def test_four_classic_needs_only_three_submodels():
    # other si ricava per sottrazione: mai più di 3 sotto-modelli sul ft.
    p = plan(make_job(K.VOCALS, K.DRUMS, K.BASS, K.OTHER))
    first = p.passes[0]
    assert first.mode == "partial"
    assert set(first.needed) == {K.BASS, K.DRUMS, K.VOCALS}
    assert first.units == 3.0


def test_guitar_forces_6s_single_pass():
    p = plan(make_job(K.VOCALS, K.GUITAR))
    assert p.first_stage_model == "htdemucs_6s"
    first = p.passes[0]
    assert first.mode == "full"
    assert first.units == 1.0


def test_piano_forces_6s_even_alone():
    p = plan(make_job(K.PIANO))
    assert p.first_stage_model == "htdemucs_6s"


def test_instrumental_only_runs_vocals_submodel():
    p = plan(make_job(K.INSTRUMENTAL))
    first = p.passes[0]
    assert first.needed == (K.VOCALS,)
    assert first.units == 1.0
    assert p.write == (K.INSTRUMENTAL,)


def test_vocals_plus_instrumental_still_one_submodel():
    p = plan(make_job(K.VOCALS, K.INSTRUMENTAL))
    assert p.passes[0].units == 1.0


def test_other_alone_uses_other_submodel():
    p = plan(make_job(K.OTHER))
    first = p.passes[0]
    assert first.mode == "partial"
    assert first.needed == (K.OTHER,)


def test_other_alone_best_is_full():
    p = plan(make_job(K.OTHER, quality="best"))
    assert p.passes[0].mode == "full"


# --- secondo stadio: chiusura dipendenze ---------------------------------


def test_kick_without_drums_computes_drums():
    p = plan(make_job(K.KICK))
    assert backends_of(p) == ["demucs4", "drumsplit"]
    assert p.passes[0].needed == (K.DRUMS,)
    assert p.passes[1].input_stem == K.DRUMS
    assert p.passes[1].needed == (K.KICK,)
    # drums non è scritto: non era stato chiesto (§5.3 punto 1)
    assert p.write == (K.KICK,)


def test_lead_with_dereverb_order():
    # il de-riverbero precede lo split lead/cori: lavora sulla voce asciutta
    p = plan(make_job(K.LEAD_VOCALS, dereverb=True))
    assert backends_of(p) == ["demucs4", "dereverb", "vocalsplit"]
    assert p.passes[0].needed == (K.VOCALS,)


def test_derived_from_both_families():
    p = plan(make_job(K.KICK, K.LEAD_VOCALS))
    assert backends_of(p) == ["demucs4", "drumsplit", "vocalsplit"]
    assert set(p.passes[0].needed) == {K.DRUMS, K.VOCALS}


def test_everything_with_dereverb():
    p = plan(
        make_job(
            K.VOCALS, K.DRUMS, K.BASS, K.GUITAR, K.PIANO, K.OTHER, K.INSTRUMENTAL,
            K.KICK, K.SNARE, K.TOMS, K.HIHAT, K.CYMBALS,
            K.LEAD_VOCALS, K.BACKING_VOCALS,
            dereverb=True,
        )
    )
    assert p.first_stage_model == "htdemucs_6s"
    assert backends_of(p) == ["demucs4", "drumsplit", "dereverb", "vocalsplit"]
    assert set(p.passes[1].needed) == {K.KICK, K.SNARE, K.TOMS, K.HIHAT, K.CYMBALS}


def test_dereverb_alone_computes_vocals():
    p = plan(make_job(K.VOCALS, dereverb=True))
    assert backends_of(p) == ["demucs4", "dereverb"]


# --- sottrazione senza doppi conteggi ------------------------------------


def test_subtraction_skips_derived_covered_by_base():
    terms = subtraction_terms((K.VOCALS, K.DRUMS, K.KICK, K.OTHER))
    assert terms == (K.VOCALS, K.DRUMS)  # kick è già dentro drums


def test_subtraction_uses_derived_when_base_missing():
    terms = subtraction_terms((K.VOCALS, K.KICK, K.SNARE, K.OTHER))
    assert terms == (K.VOCALS, K.KICK, K.SNARE)


def test_subtraction_ignores_residuals():
    assert subtraction_terms((K.OTHER, K.INSTRUMENTAL)) == ()


# --- stima: il tempo scala con quanto si chiede (O7) ---------------------


def test_estimate_scales_with_request():
    duration = 240.0
    one = estimate_seconds(plan(make_job(K.VOCALS)), duration, DEFAULT_RATES)
    two = estimate_seconds(plan(make_job(K.VOCALS, K.DRUMS)), duration, DEFAULT_RATES)
    four = estimate_seconds(
        plan(make_job(K.VOCALS, K.DRUMS, K.BASS, K.OTHER)), duration, DEFAULT_RATES
    )
    assert one < two < four
    assert one < 0.35 * four / 0.75  # 1 vs 3 sotto-modelli: ben sotto il tetto


def test_best_costs_more_than_balanced():
    duration = 240.0
    balanced = estimate_seconds(plan(make_job(K.VOCALS)), duration, DEFAULT_RATES)
    best = estimate_seconds(
        plan(make_job(K.VOCALS, quality="best")), duration, DEFAULT_RATES
    )
    # insieme completo (4x) + shifts=2 (3x) + overlap: ordine di grandezza
    assert best > 10 * balanced


def test_fast_cheaper_than_balanced():
    duration = 240.0
    fast = estimate_seconds(plan(make_job(K.VOCALS, quality="fast")), duration, DEFAULT_RATES)
    balanced = estimate_seconds(plan(make_job(K.VOCALS)), duration, DEFAULT_RATES)
    assert fast < balanced


def test_second_stage_adds_fraction_not_multiple():
    duration = 240.0
    base = estimate_seconds(
        plan(make_job(K.VOCALS, K.DRUMS, K.BASS, K.OTHER)), duration, DEFAULT_RATES
    )
    with_split = estimate_seconds(
        plan(make_job(K.VOCALS, K.DRUMS, K.BASS, K.OTHER, K.KICK)),
        duration,
        DEFAULT_RATES,
    )
    assert base < with_split < base * 1.5


# --- validazione job ------------------------------------------------------


def test_job_rejects_duplicates():
    with pytest.raises(ValueError):
        make_job(K.VOCALS, K.VOCALS)


def test_job_rejects_empty():
    with pytest.raises(ValueError):
        SeparationJob(
            source=Path("x.wav"), wanted=(), quality="best", out_dir=Path("out")
        )
