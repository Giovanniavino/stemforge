"""Gate licenze di notarize.sh (BUILD_SPEC §5.8 punto 3), senza Mac.

Il gate e' Python puro: si collauda su un finto repo con moduli di
engine/ scritti nei modi in cui WEIGHTS_SHA256 puo' comparire.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("license_gate", ROOT / "packaging" / "macos" / "license_gate.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules["license_gate"] = gate
_spec.loader.exec_module(gate)

SHA = "ab" * 32


def make_repo(tmp_path: Path, modules: dict[str, str], cleared: str | None = None) -> Path:
    engine = tmp_path / "src" / "stemforge" / "engine"
    engine.mkdir(parents=True)
    for name, source in modules.items():
        (engine / f"{name}.py").write_text(source, encoding="utf-8")
    if cleared is not None:
        (tmp_path / "packaging").mkdir()
        (tmp_path / "packaging" / "cleared_licenses.txt").write_text(cleared, encoding="utf-8")
    return tmp_path


def test_the_real_repo_passes_today():
    # nessun modello di 2° stadio adottato: WEIGHTS_SHA256 = None ovunque
    assert gate.blocked(ROOT) == []


def test_not_adopted_models_pass(tmp_path):
    repo = make_repo(tmp_path, {
        "drumsplit": "WEIGHTS_SHA256: str | None = None  # non adottato\n",
        "demucs4": "MODEL = 'htdemucs_ft'\n",
    })
    assert gate.blocked(repo) == []


def test_adopted_without_clearance_is_blocked(tmp_path):
    repo = make_repo(tmp_path, {"vocalsplit": f'WEIGHTS_SHA256: str | None = "{SHA}"\n'})
    assert gate.blocked(repo) == [f"vocalsplit:{SHA}"]
    assert gate.main(["--root", str(repo)]) == 1


def test_adopted_and_cleared_passes_only_for_that_exact_hash(tmp_path, capsys):
    other = "cd" * 32
    repo = make_repo(
        tmp_path,
        {"vocalsplit": f'WEIGHTS_SHA256 = "{SHA}"\n', "dereverb": f'WEIGHTS_SHA256 = "{other}"\n'},
        cleared=f"# verificata per iscritto il 01-12-2026\nvocalsplit:{SHA}\ndereverb:{SHA}\n",
    )
    # dereverb ha cambiato peso: la licenza verificata era di un altro file
    assert gate.blocked(repo) == [f"dereverb:{other}"]
    capsys.readouterr()


def test_values_the_gate_cannot_read_block(tmp_path):
    repo = make_repo(tmp_path, {
        "roformer": "WEIGHTS_SHA256 = _load_hash()\n",
        "broken": "WEIGHTS_SHA256 = (\n",
    })
    problems = gate.blocked(repo)
    assert len(problems) == 2
    assert all("non e' None" in line for line in problems)


def test_wrong_root_is_an_error_not_a_pass(tmp_path, capsys):
    assert gate.main(["--root", str(tmp_path)]) == 1
    assert "radice del repo sbagliata" in capsys.readouterr().err
