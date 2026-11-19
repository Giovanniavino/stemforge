"""compat.load_checkpoint: hash sempre verificato, pickle ristretto dove
torch lo consente. Checkpoint finti generati qui, con la stessa forma di
quelli di demucs (classe del modello, Fraction, scalari numpy)."""

from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("demucs")

from demucs.htdemucs import HTDemucs  # noqa: E402

from stemforge.engine import compat, paths  # noqa: E402

pytestmark = pytest.mark.compat

FT_CHECKPOINTS = ("f7e0c4bc-ba3fe64a.th", "d12395a8-e57c48e6.th",
                  "92cfc3b6-ef3bcb9c.th", "04573f0d-f3cf25b2.th")

_calls: list[str] = []


def _record(tag: str) -> str:
    _calls.append(tag)
    return tag


class _Payload:
    """Oggetto che, se scompattato, esegue una funzione: un pickle ostile."""

    def __reduce__(self):
        return (_record, ("eseguito",))


def _save_named_by_hash(tmp_path: Path, package: object) -> Path:
    raw = tmp_path / "raw.th"
    torch.save(package, raw)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    return raw.rename(tmp_path / f"0123abcd-{digest[:8]}.th")


def _demucs_like_package() -> dict:
    return {
        "klass": HTDemucs,
        "args": (),
        "kwargs": {"sources": ["drums", "bass"], "segment": Fraction(39, 5)},
        "state": {"weight": torch.arange(6, dtype=torch.float32).reshape(2, 3)},
        "metrics": (np.float64(0.25), np.dtype("float64")),
    }


def test_demucs_like_checkpoint_loads_with_hash_checked(tmp_path):
    path = _save_named_by_hash(tmp_path, _demucs_like_package())

    package = compat.load_checkpoint(path)

    assert package["klass"] is HTDemucs
    assert package["kwargs"]["segment"] == Fraction(39, 5)
    assert torch.equal(package["state"]["weight"], torch.arange(6.0).reshape(2, 3))
    assert float(package["metrics"][0]) == 0.25


def test_tampered_checkpoint_is_refused_before_unpickling(tmp_path):
    path = _save_named_by_hash(tmp_path, {"state": {"w": torch.ones(4)}, "x": _Payload()})
    data = bytearray(path.read_bytes())
    data[-10] ^= 0xFF
    path.write_bytes(bytes(data))
    _calls.clear()

    with pytest.raises(compat.CheckpointError, match="alterato"):
        compat.load_checkpoint(path)
    assert _calls == []


def test_checkpoint_without_hash_in_name_is_refused(tmp_path):
    path = tmp_path / "modello.th"
    torch.save({"state": {}}, path)

    with pytest.raises(compat.CheckpointError, match="hash"):
        compat.load_checkpoint(path)


def test_missing_checkpoint_is_a_checkpoint_error(tmp_path):
    with pytest.raises(compat.CheckpointError, match="illeggibili"):
        compat.verify_checkpoint(tmp_path / "0123abcd-deadbeef.th")


def test_hash_prefix_comes_from_the_name():
    assert compat.expected_hash_prefix(Path("f7e0c4bc-ba3fe64a.th")) == "ba3fe64a"
    assert compat.expected_hash_prefix(Path("x-y-0a1b2c3d4e.th")) == "0a1b2c3d4e"
    with pytest.raises(compat.CheckpointError):
        compat.expected_hash_prefix(Path("f7e0c4bc-BA3FE64A.th"))


def test_hostile_pickle_with_right_hash_is_refused_where_torch_allows(tmp_path):
    if not compat.has_weights_only_allowlist():
        pytest.skip(f"torch {torch.__version__}: weights_only non estendibile, protegge solo l'hash")
    path = _save_named_by_hash(tmp_path, {"state": {}, "x": _Payload()})
    _calls.clear()

    with pytest.raises(Exception, match="(?i)weights only|unpickl"):
        compat.load_checkpoint(path)
    assert _calls == []


def test_allowlist_names_resolve_in_this_environment():
    entries = compat._allowlist(compat.DEMUCS_SAFE_GLOBALS)
    names = {e[1] for e in entries if isinstance(e, tuple)}
    names |= {f"{e.__module__}.{e.__name__}" for e in entries if not isinstance(e, tuple)}
    assert set(compat.DEMUCS_SAFE_GLOBALS) <= names


@pytest.fixture()
def system_checkpoints(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cartella dei pesi veri (solo lettura): il conftest comune la isola."""
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    return paths.models_dir() / "checkpoints"


@pytest.mark.slow  # pesi veri, ~80 MB l'uno: fuori dal giro veloce, dentro -m compat
@pytest.mark.parametrize("name", FT_CHECKPOINTS)
def test_real_htdemucs_ft_weights_build_the_model(name, system_checkpoints):
    path = system_checkpoints / name
    if not path.is_file():
        pytest.skip(f"pesi {name} non scaricati su questa macchina")
    from demucs.states import load_model

    model = load_model(compat.load_checkpoint(path))

    assert isinstance(model, HTDemucs)
    assert model.sources == ["drums", "bass", "other", "vocals"]


@pytest.mark.slow
def test_real_weights_are_the_same_tensors_as_a_full_load(system_checkpoints):
    present = [system_checkpoints / n for n in FT_CHECKPOINTS if (system_checkpoints / n).is_file()]
    if not present:
        pytest.skip("pesi htdemucs_ft non scaricati su questa macchina")
    ours = compat.load_checkpoint(present[0])["state"]
    full = torch.load(present[0], map_location="cpu", weights_only=False)["state"]

    assert ours.keys() == full.keys()
    assert all(torch.equal(ours[key], full[key]) for key in full)
