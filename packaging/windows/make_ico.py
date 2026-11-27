"""Icona dell'installer Windows: packaging/build/icon.ico da packaging/icon.png.

    python packaging/windows/make_ico.py [destinazione.ico]

Inno Setup (SetupIconFile) vuole un .ico vero, non un .png: lo si genera
alla build invece di tenerne una copia binaria nel repo che può
divergere dall'icona dell'app. Dentro ci sono tutte le misure che Windows
chiede (dalla barra delle applicazioni a 16 px fino a Esplora risorse a
256 px), così nessuna viene ricampionata male al volo.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parents[1]
SOURCE = PACKAGING / "icon.png"
DEFAULT_TARGET = PACKAGING / "build" / "icon.ico"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def make_ico(source: Path, target: Path) -> list[tuple[int, int]]:
    from PIL import Image

    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.convert("RGBA").save(target, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    with Image.open(target) as written:
        return sorted(written.info["sizes"])


def main() -> int:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_TARGET
    sizes = make_ico(SOURCE, target)
    missing = sorted({(s, s) for s in ICO_SIZES} - set(sizes))
    if missing:
        print(f"misure mancanti in {target}: {missing}", file=sys.stderr)
        return 1
    print(f"icona scritta: {target} ({len(sizes)} misure, {sizes[0][0]}..{sizes[-1][0]} px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
