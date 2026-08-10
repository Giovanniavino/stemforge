"""Unitari del livello model: job, manifest, stem specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from stemforge.model.job import SeparationJob
from stemforge.model.manifest import Manifest, ManifestSchemaError
from stemforge.model.stem import CONCRETE_BASE, SPECS, StemKind, derived_of, is_derived


def test_every_kind_has_a_spec():
    assert set(SPECS) == set(StemKind)


def test_derived_point_to_base():
    for kind, spec in SPECS.items():
        if spec.stage == 2:
            assert spec.derives_from is not None
            assert SPECS[spec.derives_from].stage == 1
        else:
            assert spec.derives_from is None


def test_derived_of_drums():
    assert derived_of(StemKind.DRUMS) == {
        StemKind.KICK, StemKind.SNARE, StemKind.TOMS, StemKind.HIHAT, StemKind.CYMBALS
    }


def test_residuals_are_not_concrete():
    assert StemKind.OTHER not in CONCRETE_BASE
    assert StemKind.INSTRUMENTAL not in CONCRETE_BASE
    assert not is_derived(StemKind.OTHER)


def test_job_json_roundtrip():
    job = SeparationJob(
        source=Path("C:/musica/brano.mp3"),
        wanted=(StemKind.VOCALS, StemKind.KICK),
        quality="best",
        out_dir=Path("C:/out"),
        fmt="flac",
        device="cpu",
        dereverb_vocals=True,
    )
    again = SeparationJob.from_json(job.to_json())
    assert again == job


def test_job_rejects_bad_quality():
    with pytest.raises(ValueError):
        SeparationJob(
            source=Path("x.wav"),
            wanted=(StemKind.VOCALS,),
            quality="turbo",
            out_dir=Path("out"),
        )


MANIFEST_JSON = """
{
  "schema": 1,
  "source": { "name": "brano.mp3", "sha1": "abc", "duration_s": 214.7 },
  "audio":  { "samplerate": 44100, "channels": 2, "bit_depth": 24 },
  "engine": { "backend": "demucs", "model": "htdemucs_ft",
              "quality": "best", "version": "0.1.0" },
  "stems": [
    { "kind": "vocals", "file": "vocals.wav",
      "peak_dbfs": -1.2, "rms_dbfs": -18.4 }
  ],
  "created_utc": "2026-08-10T14:22:31Z"
}
"""


def test_manifest_roundtrip():
    manifest = Manifest.from_json(MANIFEST_JSON)
    assert manifest.source.name == "brano.mp3"
    assert manifest.stems[0].kind == StemKind.VOCALS
    assert manifest.dereverb is False
    again = Manifest.from_json(manifest.to_json())
    assert again == manifest


def test_manifest_rejects_unknown_schema():
    bad = MANIFEST_JSON.replace('"schema": 1', '"schema": 99')
    with pytest.raises(ManifestSchemaError):
        Manifest.from_json(bad)
