"""Manifest: il contratto stabile scritto accanto agli stem.

BUILD_SPEC §4.3. Questo modulo converte da e verso JSON ma NON tocca il
disco: la scrittura del file sta in export/folder.py, la lettura in chi
la usa. È la regola "model = zero I/O" (§10.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from stemforge.model.job import StemFile
from stemforge.model.stem import StemKind

SCHEMA_VERSION = 1


class ManifestSchemaError(ValueError):
    """Schema non riconosciuto: il reader rifiuta con errore chiaro (§4.3)."""


@dataclass(frozen=True)
class SourceInfo:
    name: str
    sha1: str
    duration_s: float


@dataclass(frozen=True)
class AudioInfo:
    samplerate: int
    channels: int
    bit_depth: int


@dataclass(frozen=True)
class EngineInfo:
    backend: str
    model: str
    quality: str
    version: str


@dataclass(frozen=True)
class Manifest:
    source: SourceInfo
    audio: AudioInfo
    engine: EngineInfo
    stems: tuple[StemFile, ...]
    created_utc: str  # ISO 8601, es. "2026-08-10T14:22:31Z"
    dereverb: bool = False  # §5.2.3: rompe l'invariante, va dichiarato

    def to_json(self) -> str:
        data = {
            "schema": SCHEMA_VERSION,
            "source": {
                "name": self.source.name,
                "sha1": self.source.sha1,
                "duration_s": self.source.duration_s,
            },
            "audio": {
                "samplerate": self.audio.samplerate,
                "channels": self.audio.channels,
                "bit_depth": self.audio.bit_depth,
            },
            "engine": {
                "backend": self.engine.backend,
                "model": self.engine.model,
                "quality": self.engine.quality,
                "version": self.engine.version,
            },
            "stems": [
                {
                    "kind": s.kind.value,
                    "file": s.file,
                    "peak_dbfs": s.peak_dbfs,
                    "rms_dbfs": s.rms_dbfs,
                }
                for s in self.stems
            ],
            "created_utc": self.created_utc,
        }
        if self.dereverb:
            data["dereverb"] = True
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> Manifest:
        data = json.loads(raw)
        schema = data.get("schema")
        if schema != SCHEMA_VERSION:
            raise ManifestSchemaError(
                f"manifest con schema {schema!r} non supportato: "
                f"questa versione di StemForge legge solo lo schema {SCHEMA_VERSION}"
            )
        return cls(
            source=SourceInfo(
                name=data["source"]["name"],
                sha1=data["source"]["sha1"],
                duration_s=float(data["source"]["duration_s"]),
            ),
            audio=AudioInfo(
                samplerate=int(data["audio"]["samplerate"]),
                channels=int(data["audio"]["channels"]),
                bit_depth=int(data["audio"]["bit_depth"]),
            ),
            engine=EngineInfo(
                backend=data["engine"]["backend"],
                model=data["engine"]["model"],
                quality=data["engine"]["quality"],
                version=data["engine"]["version"],
            ),
            stems=tuple(
                StemFile(
                    kind=StemKind(s["kind"]),
                    file=s["file"],
                    peak_dbfs=float(s["peak_dbfs"]),
                    rms_dbfs=float(s["rms_dbfs"]),
                )
                for s in data["stems"]
            ),
            created_utc=data["created_utc"],
            dereverb=bool(data.get("dereverb", False)),
        )
