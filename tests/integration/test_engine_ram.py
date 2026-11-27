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
# Una RAM in cui una passata regge solo 20 s di audio, stem a lunghezza
# piena compresi: si ricava dalle costanti misurate invece di fissare un
# numero che smetterebbe di dividere al prossimo aggiornamento delle misure.
_FITS_S = 20.0
LOW_RAM = int(
    (blocks.PASS_FIXED_BYTES + _FITS_S * blocks.PASS_BYTES_PER_AUDIO_S) / blocks.RAM_FRACTION
    + blocks.output_bytes(3, 2, int(SONG_S * SR))
)


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

    usable = blocks.memory_for_blocks(LOW_RAM, blocks.output_bytes(3, 2, int(SONG_S * SR)))
    limit = int(blocks.block_length_s(usable) * SR)
    assert readings == [LOW_RAM], "la RAM si legge una volta per passata, a modello caricato"
    assert len(fake.chunk_frames) > 1, "con poca RAM 45 s non vanno in una passata sola"
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


class _EchoBackend:
    """Restituisce il blocco ricevuto per ogni sorgente: basta a contare i blocchi."""

    samplerate = SR

    def __init__(self) -> None:
        self.chunk_frames: list[int] = []

    def separate(self, audio, wanted, on_progress, should_cancel):
        self.chunk_frames.append(int(audio.shape[-1]))
        return {kind: audio.clone() for kind in wanted}


def test_full_length_stems_are_reserved_before_sizing_the_blocks():
    # Gli stem a lunghezza piena restano in RAM qualunque sia il blocco:
    # una RAM che basterebbe al brano intero SENZA contarli deve dividere.
    from stemforge.worker.passes import run_pass_blocks

    seconds = 60.0
    frames = int(seconds * SR)
    wanted = frozenset({K.VOCALS, K.DRUMS, K.BASS, K.OTHER})
    pass_only = blocks.PASS_FIXED_BYTES + seconds * blocks.PASS_BYTES_PER_AUDIO_S
    available = int(pass_only / blocks.RAM_FRACTION) + 1_000_000
    assert len(blocks.split_blocks(frames, SR, available)) == 1, "premessa del test"

    backend = _EchoBackend()
    work = np.zeros((2, frames), dtype=np.float32)
    out = run_pass_blocks(backend, work, wanted, lambda v: None, lambda: False, lambda: available)
    assert len(backend.chunk_frames) > 1
    assert all(o.shape == (2, frames) for o in out.values())


def test_memory_for_blocks_never_goes_negative():
    assert blocks.memory_for_blocks(None, 10**9) is None
    assert blocks.memory_for_blocks(10**9, 2 * 10**9) == 0
    assert blocks.memory_for_blocks(3 * 10**9, 10**9) == 2 * 10**9
