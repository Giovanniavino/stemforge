"""Blocchi/overlap-add (§5.7 regola 6), lunghezze, naming cartelle (§7.3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from stemforge.engine.audio_io import (
    BLOCK_THRESHOLD_S,
    match_length,
    overlap_add,
    split_blocks,
    to_original_channels,
)
from stemforge.export.folder import allocate_out_dir


def test_short_file_is_one_block():
    assert len(split_blocks(44100 * 60, 44100)) == 1


def test_long_file_splits_with_overlap():
    frames = int(44100 * (BLOCK_THRESHOLD_S + 600))  # 25 minuti
    blocks = split_blocks(frames, 44100)
    assert len(blocks) > 1
    assert blocks[0].fade_in == 0
    for prev, cur in zip(blocks, blocks[1:]):
        assert cur.fade_in > 0
        assert cur.start == prev.end - cur.fade_in  # si sovrappongono
    assert blocks[-1].end == frames


def test_overlap_add_reconstructs_identity():
    # rampe complementari: se i blocchi portano lo stesso segnale,
    # la ricomposizione è il segnale, esattamente (w + (1-w) = 1).
    frames = int(44100 * (BLOCK_THRESHOLD_S + 120))
    rng = np.random.default_rng(seed=1)
    signal = rng.standard_normal((2, frames)).astype(np.float32)
    blocks = split_blocks(frames, 44100)
    out = np.zeros_like(signal)
    for block in blocks:
        overlap_add(out, signal[:, block.start : block.end], block)
    np.testing.assert_allclose(out, signal, atol=1e-6)


def test_match_length_trims_and_pads():
    audio = np.ones((2, 100), dtype=np.float32)
    assert match_length(audio, 80).shape == (2, 80)
    padded = match_length(audio, 130)
    assert padded.shape == (2, 130)
    assert np.all(padded[:, 100:] == 0)
    assert match_length(audio, 100) is audio


def test_mono_roundtrip_is_exact():
    mono = np.random.default_rng(2).standard_normal((1, 500)).astype(np.float32)
    stereo = np.repeat(mono, 2, axis=0)
    back = to_original_channels(stereo, 1)
    np.testing.assert_array_equal(back, mono)


def test_out_dir_collision_gets_suffix(tmp_path: Path):
    first = allocate_out_dir(tmp_path, "Brano.mp3")
    second = allocate_out_dir(tmp_path, "Brano.mp3")
    third = allocate_out_dir(tmp_path, "Brano.mp3")
    assert first.name == "Brano"
    assert second.name == "Brano (2)"
    assert third.name == "Brano (3)"
    assert first.exists() and second.exists() and third.exists()
