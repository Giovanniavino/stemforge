"""compat.get_demucs_model / VerifiedRemoteRepo: i modelli ufficiali di
demucs caricati da load_checkpoint, con torch 2.2.2 e 2.10. Un HTDemucs
minuscolo costruito qui fa da checkpoint: nessun peso vero, nessuna rete."""

from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("demucs")

from demucs.apply import BagOfModels  # noqa: E402
from demucs.htdemucs import HTDemucs  # noqa: E402
from demucs.repo import ModelLoadingError  # noqa: E402
from demucs.states import get_state, load_model  # noqa: E402

from stemforge.engine import compat, paths  # noqa: E402

pytestmark = pytest.mark.compat

SIG = "0123abcd"
TINY_KWARGS = {"sources": ["drums", "bass"], "channels": 8, "depth": 2, "t_layers": 1,
               "segment": Fraction(39, 5)}
URL_ROOT = "https://dl.fbaipublicfiles.invalid/demucs/hybrid_transformer/"


def _tiny_package() -> dict:
    torch.manual_seed(0)
    model = HTDemucs(**TINY_KWARGS)
    return {"klass": HTDemucs, "args": (), "kwargs": dict(TINY_KWARGS),
            "state": get_state(model, None)}


def _named_checkpoint(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    raw = folder / "raw.th"
    torch.save(_tiny_package(), raw)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    return raw.rename(folder / f"{SIG}-{digest[:8]}.th")


def test_plain_torch_load_is_the_real_difference(tmp_path):
    # demucs.states.load_model(percorso) fa torch.load col default: va con
    # torch 2.2.2, rifiuta i checkpoint demucs con torch 2.10
    path = _named_checkpoint(tmp_path)
    if compat.torch_version() < (2, 6):
        assert isinstance(load_model(path), HTDemucs)
    else:
        with pytest.raises(Exception, match="(?i)weights only|unpickl"):
            load_model(path)


def test_cached_checkpoint_builds_the_model_without_network(tmp_path, monkeypatch):
    path = _named_checkpoint(tmp_path / "checkpoints")
    monkeypatch.setattr(torch.hub, "download_url_to_file",
                        lambda *a, **k: pytest.fail("pesi gia' presenti: niente download"))
    repo = compat.VerifiedRemoteRepo({SIG: URL_ROOT + path.name}, tmp_path / "checkpoints")

    model = repo.get_model(SIG)

    expected = torch.load(path, map_location="cpu", weights_only=False)["state"]
    assert isinstance(model, HTDemucs) and model.sources == ["drums", "bass"]
    torch.testing.assert_close(model.state_dict(), expected, rtol=0, atol=0)


def test_missing_checkpoint_is_downloaded_with_the_hash_prefix(tmp_path, monkeypatch):
    source = _named_checkpoint(tmp_path / "server")
    calls: list[tuple[str, str]] = []

    def fake_download(url: str, dst: str, hash_prefix: str | None = None, **_: object) -> None:
        calls.append((url, hash_prefix or ""))
        Path(dst).write_bytes(source.read_bytes())

    monkeypatch.setattr(torch.hub, "download_url_to_file", fake_download)
    checkpoints = tmp_path / "hub" / "checkpoints"
    repo = compat.VerifiedRemoteRepo({SIG: URL_ROOT + source.name}, checkpoints)

    assert isinstance(repo.get_model(SIG), HTDemucs)
    assert calls == [(URL_ROOT + source.name, source.name.split("-")[1][:8])]
    assert (checkpoints / source.name).is_file()


def _corrupt(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))


def test_corrupted_cached_checkpoint_is_downloaded_again(tmp_path, monkeypatch):
    # §9.2: un peso danneggiato si riconosce e si riscarica, non si carica
    source = _named_checkpoint(tmp_path / "server")
    checkpoints = tmp_path / "hub" / "checkpoints"
    checkpoints.mkdir(parents=True)
    cached = checkpoints / source.name
    cached.write_bytes(source.read_bytes())
    _corrupt(cached)
    calls: list[str] = []

    def fake_download(url: str, dst: str, hash_prefix: str | None = None, **_: object) -> None:
        calls.append(url)
        Path(dst).write_bytes(source.read_bytes())

    monkeypatch.setattr(torch.hub, "download_url_to_file", fake_download)
    repo = compat.VerifiedRemoteRepo({SIG: URL_ROOT + source.name}, checkpoints)

    assert isinstance(repo.get_model(SIG), HTDemucs)
    assert calls == [URL_ROOT + source.name]
    assert cached.read_bytes() == source.read_bytes()


def test_corrupted_checkpoint_is_never_loaded_when_offline(tmp_path, monkeypatch):
    path = _named_checkpoint(tmp_path)
    _corrupt(path)

    def offline(*_: object, **__: object) -> None:
        raise OSError("rete assente")

    monkeypatch.setattr(torch.hub, "download_url_to_file", offline)
    repo = compat.VerifiedRemoteRepo({SIG: URL_ROOT + path.name}, tmp_path)

    with pytest.raises(OSError, match="rete assente"):
        repo.get_model(SIG)
    assert not path.exists()


def test_unknown_signature_is_a_demucs_loading_error(tmp_path):
    repo = compat.VerifiedRemoteRepo({}, tmp_path)

    assert not repo.has_model(SIG)
    with pytest.raises(ModelLoadingError, match=SIG):
        repo.get_model(SIG)


@pytest.mark.slow
def test_real_htdemucs_ft_bag_loads_from_the_hub_cache(monkeypatch):
    # pesi veri gia' scaricati sul dev-box: ~80 MB a modello, da qui "slow"
    monkeypatch.delenv("STEMFORGE_MODELS", raising=False)
    hub = paths.models_dir()
    if not (hub / "checkpoints").is_dir():
        pytest.skip("pesi htdemucs_ft non scaricati su questa macchina")
    monkeypatch.setattr(torch.hub, "download_url_to_file",
                        lambda *a, **k: pytest.skip("un peso di htdemucs_ft manca"))
    previous = torch.hub.get_dir()
    torch.hub.set_dir(str(hub))
    try:
        model = compat.get_demucs_model("htdemucs_ft")
    finally:
        torch.hub.set_dir(previous)

    assert isinstance(model, BagOfModels) and len(model.models) == 4
    assert all(isinstance(sub, HTDemucs) and not sub.training for sub in model.models)
    assert model.sources == ["drums", "bass", "other", "vocals"]
