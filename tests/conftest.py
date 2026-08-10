"""Fixture condivise: audio sintetico generato in codice (§10.2).

Niente materiale protetto da copyright: sinusoide + rumore + click,
8 secondi, deterministico (seed fisso).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

FIXTURE_SECONDS = 8.0


def synth_mix(samplerate: int, seconds: float = FIXTURE_SECONDS, channels: int = 2) -> np.ndarray:
    """[channels, samples] float32: sinusoidi + rumore + click."""
    n = int(seconds * samplerate)
    t = np.arange(n, dtype=np.float64) / samplerate
    rng = np.random.default_rng(seed=42)
    base = (
        0.35 * np.sin(2 * np.pi * 220.0 * t)
        + 0.15 * np.sin(2 * np.pi * 3300.0 * t) * np.exp(-((t % 1.0) * 6.0))
        + 0.05 * rng.standard_normal(n)
    )
    clicks = np.zeros(n)
    clicks[:: samplerate // 2] = 0.6
    mono = (base + clicks).astype(np.float32)
    peak = np.max(np.abs(mono))
    mono = mono / peak * 0.89  # headroom, niente clipping
    if channels == 1:
        return mono[None, :]
    right = np.roll(mono, 7) * 0.97  # stereo non banale ma deterministico
    return np.stack([mono, right.astype(np.float32)])


def write_fixture(path: Path, samplerate: int, channels: int = 2,
                  seconds: float = FIXTURE_SECONDS) -> Path:
    import soundfile as sf

    audio = synth_mix(samplerate, seconds, channels)
    sf.write(path, audio.T, samplerate, subtype="PCM_24")
    return path


@pytest.fixture()
def mix_44k(tmp_path: Path) -> Path:
    return write_fixture(tmp_path / "brano.wav", 44100)


@pytest.fixture()
def mix_48k(tmp_path: Path) -> Path:
    return write_fixture(tmp_path / "brano48.wav", 48000)


@pytest.fixture()
def mix_mono(tmp_path: Path) -> Path:
    return write_fixture(tmp_path / "mono.wav", 44100, channels=1)


@pytest.fixture(autouse=True)
def isolated_calibration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ogni test ha la sua calibration.json: niente stato condiviso."""
    monkeypatch.setenv("STEMFORGE_CALIBRATION", str(tmp_path / "calibration.json"))
    monkeypatch.setenv("STEMFORGE_MODELS", str(tmp_path / "models"))
