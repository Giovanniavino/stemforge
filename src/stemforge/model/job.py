"""SeparationJob e JobResult: la richiesta immutabile e il suo esito.

BUILD_SPEC §4.2. Il job attraversa il confine fra processi come JSON
(stdin del worker, D2): la serializzazione vive qui, la scrittura su
disco no (questo livello non fa I/O).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stemforge.model.stem import StemKind

QUALITIES = ("fast", "balanced", "best")
FORMATS = ("wav", "flac")
DEVICES = ("auto", "cpu", "cuda")


@dataclass(frozen=True)
class SeparationJob:
    source: Path
    wanted: tuple[StemKind, ...]
    quality: str  # "fast" | "balanced" | "best"
    out_dir: Path
    fmt: str = "wav"  # "wav" | "flac"
    device: str = "auto"  # "auto" | "cpu" | "cuda"
    dereverb_vocals: bool = False  # §5.2.3, opzione non stem

    def __post_init__(self) -> None:
        if self.quality not in QUALITIES:
            raise ValueError(f"quality sconosciuta: {self.quality!r}")
        if self.fmt not in FORMATS:
            raise ValueError(f"formato sconosciuto: {self.fmt!r}")
        if self.device not in DEVICES:
            raise ValueError(f"device sconosciuto: {self.device!r}")
        if not self.wanted:
            raise ValueError("nessuno stem richiesto")
        seen: set[StemKind] = set()
        for kind in self.wanted:
            if kind in seen:
                raise ValueError(f"stem duplicato: {kind}")
            seen.add(kind)

    def to_json(self) -> str:
        return json.dumps(
            {
                "source": str(self.source),
                "wanted": [k.value for k in self.wanted],
                "quality": self.quality,
                "out_dir": str(self.out_dir),
                "fmt": self.fmt,
                "device": self.device,
                "dereverb_vocals": self.dereverb_vocals,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> SeparationJob:
        data = json.loads(raw)
        return cls(
            source=Path(data["source"]),
            wanted=tuple(StemKind(k) for k in data["wanted"]),
            quality=data["quality"],
            out_dir=Path(data["out_dir"]),
            fmt=data["fmt"],
            device=data["device"],
            dereverb_vocals=bool(data["dereverb_vocals"]),
        )


@dataclass(frozen=True)
class StemFile:
    kind: StemKind
    file: str  # nome file relativo alla cartella del job
    peak_dbfs: float
    rms_dbfs: float


@dataclass(frozen=True)
class JobResult:
    out_dir: Path
    stems: tuple[StemFile, ...]
    # avvisi non bloccanti (2° stadio fallito, traccia quasi silenziosa...)
    warnings: tuple[str, ...] = field(default=())
