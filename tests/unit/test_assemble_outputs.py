"""assemble_outputs libera gli stem intermedi senza cambiare il risultato."""

import numpy as np

from stemforge.engine import audio_io
from stemforge.model.stem import StemKind
from stemforge.worker.assemble import assemble_outputs


def test_svuota_gli_intermedi_e_other_resta_esatto() -> None:
    rng = np.random.default_rng(0)
    mix = rng.standard_normal((2, 1000)).astype(np.float32)
    source = audio_io.SourceAudio(mix, audio_io.MODEL_SAMPLERATE, 2, 1000)
    parts = {k: rng.standard_normal((2, 1000)).astype(np.float32)
             for k in (StemKind.VOCALS, StemKind.DRUMS, StemKind.BASS, StemKind.OTHER)}
    stage1 = dict(parts)
    stems = dict(parts)
    write = (StemKind.VOCALS, StemKind.DRUMS, StemKind.OTHER)

    out = assemble_outputs(write, source, stage1, stems)

    # resta solo `other` (serve a _residuals); BASS mai scritto: eliminato
    assert stage1 == {} and set(stems) == {StemKind.OTHER}
    assert set(out) == set(write)
    np.testing.assert_array_equal(out[StemKind.VOCALS], parts[StemKind.VOCALS])
    expected = mix - parts[StemKind.VOCALS] - parts[StemKind.DRUMS]
    np.testing.assert_array_equal(out[StemKind.OTHER], expected)
