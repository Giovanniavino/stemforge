"""Gate licenze della distribuzione firmata (BUILD_SPEC §5.8 punto 3, §9.3).

    python packaging/macos/license_gate.py [--root <repo>]

Una build distribuita a terzi non può contenere pesi con licenza
non-commercial o non verificata. Un modello di 2° stadio è "adottato"
quando il suo modulo in src/stemforge/engine/ assegna a WEIGHTS_SHA256
qualcosa di diverso da None (engine/registry.py usa lo stesso segnale).
Ogni adottato deve stare in packaging/cleared_licenses.txt come
"modulo:sha256", scritto SOLO dopo aver verificato la licenza per iscritto.

Si legge il sorgente con ast, senza importarlo (niente torch qui), e ciò
che non si riesce a leggere blocca: un gate che passa quando non capisce
non è un gate.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path("src") / "stemforge" / "engine"
CLEARED = Path("packaging") / "cleared_licenses.txt"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NAME = "WEIGHTS_SHA256"


def _assigned_values(tree: ast.Module) -> list[ast.expr]:
    values: list[ast.expr] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == _NAME for target in targets):
            values.append(node.value)
    return values


def adopted_weights(engine: Path) -> tuple[dict[str, str], list[str]]:
    """({modulo: sha256} dei pesi adottati, moduli illeggibili)."""
    adopted: dict[str, str] = {}
    unreadable: list[str] = []
    for path in sorted(engine.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            unreadable.append(path.stem)
            continue
        for value in _assigned_values(tree):
            if isinstance(value, ast.Constant) and value.value is None:
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str) \
                    and _SHA256.fullmatch(value.value):
                adopted[path.stem] = value.value
            else:
                unreadable.append(path.stem)
    return adopted, unreadable


def cleared_entries(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return {line for line in lines if line}


def blocked(root: Path) -> list[str]:
    engine = root / ENGINE
    if not engine.is_dir():
        return [f"{engine} non esiste: radice del repo sbagliata?"]
    adopted, unreadable = adopted_weights(engine)
    cleared = cleared_entries(root / CLEARED)
    problems = [f"{name}: {_NAME} non e' None ne' uno sha256 letterale" for name in unreadable]
    problems += [f"{name}:{sha}" for name, sha in sorted(adopted.items())
                 if f"{name}:{sha}" not in cleared]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="radice del repo")
    problems = blocked(parser.parse_args(argv).root)
    if problems:
        print("GATE LICENZE: pesi adottati senza licenza verificata:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print(f"Aggiungi 'modulo:sha256' a {CLEARED.as_posix()} SOLO dopo aver verificato "
              "per iscritto la licenza (BUILD_SPEC §5.8).", file=sys.stderr)
        return 1
    print("gate licenze: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
