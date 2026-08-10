"""Protocollo JSON-lines UI <-> worker (D2)."""

from __future__ import annotations

import io

from stemforge.worker import protocol


def test_roundtrip_all_messages():
    messages = [
        protocol.Started(out_dir="C:/out/Brano"),
        protocol.Phase(label="Separazione — passata 1 di 3", pass_index=1, pass_count=3),
        protocol.Progress(value=0.42),
        protocol.Warning_(message="vocals.wav è quasi silenzioso"),
        protocol.Done(out_dir="C:/out/Brano", manifest="C:/out/Brano/manifest.json"),
        protocol.Error(message="Spazio insufficiente", detail="Traceback..."),
    ]
    for message in messages:
        assert protocol.decode(protocol.encode(message)) == message


def test_decode_ignores_noise():
    # librerie che stampano su stdout non devono rompere il protocollo
    assert protocol.decode("") is None
    assert protocol.decode("Downloading: 42%") is None
    assert protocol.decode('{"non": "protocollo"}') is None
    assert protocol.decode('{"type": "sconosciuto"}') is None
    assert protocol.decode('{"type": "progress"}') is None  # campo mancante


def test_write_message_is_one_line():
    stream = io.StringIO()
    protocol.write_message(stream, protocol.Progress(value=0.5))
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert protocol.decode(lines[0]) == protocol.Progress(value=0.5)
