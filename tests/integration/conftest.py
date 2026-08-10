"""Backend finto per l'integrazione: pipeline completa senza pesi (<10 s)."""

from __future__ import annotations

import time

import pytest

from stemforge.model.stem import FT_SOURCES, StemKind

# Coefficienti deterministici: la somma NON fa 1 apposta, l'invariante
# deve reggere per costruzione (sottrazione), non per gentilezza del fake.
DEFAULT_COEFFS = {
    StemKind.DRUMS: 0.21,
    StemKind.BASS: 0.13,
    StemKind.OTHER: 0.30,
    StemKind.VOCALS: 0.27,
    StemKind.GUITAR: 0.05,
    StemKind.PIANO: 0.04,
}

_CHUNKS = 10


class FakeDemucs:
    """Rispetta il contratto §5.5: progress monotòno, cancel fra chunk."""

    name = "demucs4"
    samplerate = 44100

    def __init__(self, coeffs=None, chunk_delay_s: float = 0.0, sources=FT_SOURCES):
        self.coeffs = dict(DEFAULT_COEFFS if coeffs is None else coeffs)
        self.chunk_delay_s = chunk_delay_s
        self.sources = tuple(sources)
        self.provides = frozenset(self.sources)
        self.calls: list[frozenset[StemKind]] = []

    def separate(self, audio, wanted, on_progress, should_cancel):
        from stemforge.engine.contract import CancelledError

        self.calls.append(frozenset(wanted))
        for i in range(_CHUNKS):
            if should_cancel():
                raise CancelledError("annullato")
            if self.chunk_delay_s:
                time.sleep(self.chunk_delay_s)
            on_progress((i + 1) / _CHUNKS)
        return {k: audio * self.coeffs[k] for k in wanted if k in self.coeffs}


@pytest.fixture()
def fake_backends():
    """Cache backend pre-popolata: il runner non tocca il registry."""

    def make(quality: str = "balanced", **kwargs) -> tuple[dict, FakeDemucs]:
        fake = FakeDemucs(**kwargs)
        cache = {("demucs4", "htdemucs_ft", "cpu", quality): fake,
                 ("demucs4", "htdemucs_6s", "cpu", quality): fake}
        return cache, fake

    return make


def collect_messages():
    messages: list = []

    def emit(message) -> None:
        messages.append(message)

    return messages, emit
