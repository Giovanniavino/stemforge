"""La pipeline divide in blocchi secondo la RAM che trova (BUILD_SPEC §6.1 punto 3).

RAM finta iniettata in run_job: con poca memoria un brano di 45 s va a
blocchi, con l'invariante e la lunghezza in campioni intatte.
"""

from __future__ import annotations

import numpy as np
import soundfile as sf

from stemforge.engine import blocks
from stemforge.model.job import SeparationJob
from stemforge.model.stem import StemKind as K
from stemforge.worker.pipeline import run_job

from tests.conftest import write_fixture
from tests.integration.conftest import FakeDemucs
from tests.integration.test_pipeline_fake import RECONSTRUCTION_LIMIT_DBFS, reconstruction_rms_dbfs

SR = 44100
SONG_S = 45.0
LOW_RAM = int(1.5e9)  # Mac mini da 4 GB, a modello caricato


class RecordingDemucs(FakeDemucs):
    def __init__(self) -> None:
        super().__init__()
        self.chunk_frames: list[int] = []

    def separate(self, audio, wanted, on_progress, should_cancel):
        self.chunk_frames.append(int(audio.shape[-1]))
        return super().separate(audio, wanted, on_progress, should_cancel)


def _run(tmp_path, source, available, out_name):
    fake = RecordingDemucs()
    cache = {("demucs4", "htdemucs_ft", "cpu", "balanced"): fake}
    readings: list[int | None] = []

    def probe():
        readings.append(available)
        return available

    job = SeparationJob(source=source, wanted=(K.VOCALS, K.DRUMS, K.OTHER), quality="balanced",
                        out_dir=tmp_path / out_name, device="cpu")
    result = run_job(job, lambda m: None, backends=cache, available_memory=probe)
    return result, fake, readings


def test_low_ram_splits_the_pass_and_keeps_the_invariant(tmp_path):
    source = write_fixture(tmp_path / "lungo.wav", SR, seconds=SONG_S)
    result, fake, readings = _run(tmp_path, source, LOW_RAM, "poca")

    limit = int(blocks.block_length_s(LOW_RAM) * SR)
    assert readings == [LOW_RAM], "la RAM si legge una volta per passata, a modello caricato"
    assert len(fake.chunk_frames) > 1, "con 1.5 GB 45 s non vanno in una passata sola"
    assert max(fake.chunk_frames) <= limit
    assert reconstruction_rms_dbfs(result.out_dir, source) < RECONSTRUCTION_LIMIT_DBFS
    mix, _ = sf.read(source, always_2d=True)
    for stem in result.out_dir.glob("*.wav"):
        assert sf.info(str(stem)).frames == mix.shape[0], f"{stem.name}: lunghezza diversa"


def test_blocks_give_the_same_stems_as_one_pass(tmp_path):
    source = write_fixture(tmp_path / "lungo.wav", SR, seconds=SONG_S)
    split, fake_split, _ = _run(tmp_path, source, LOW_RAM, "blocchi")
    whole, fake_whole, _ = _run(tmp_path, source, 64 * 10**9, "intero")
    assert len(fake_whole.chunk_frames) == 1 < len(fake_split.chunk_frames)
    for stem in ("vocals.wav", "drums.wav", "other.wav"):
        a, _ = sf.read(split.out_dir / stem, dtype="float32")
        b, _ = sf.read(whole.out_dir / stem, dtype="float32")
        # 24 bit: un passo di quantizzazione è 1.2e-7
        assert np.max(np.abs(a - b)) < 1e-6, stem
