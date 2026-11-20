"""Le differenze fra torch 2.2.2 (legacy-intel) e torch 2.10 (gli altri
profili) che toccano il motore. BUILD_SPEC D7: un solo motore, e se
un'API diverge la differenza sta qui e in nessun altro posto.

Censimento delle API torch/torchaudio usate da engine/ e worker/, fatto
eseguendo entrambe le versioni (tests/compat/ lo ripete a ogni giro):

- ``torch.load``: il default di ``weights_only`` e' cambiato (False nella
  2.2.2, True dalla 2.6) e solo dalla 2.5 l'elenco delle classi ammesse
  si estende con ``torch.serialization.safe_globals``. Differenza reale:
  si passa sempre per ``load_checkpoint``. Colpisce anche demucs:
  ``demucs.states.load_model(<percorso>)`` chiama ``torch.load`` senza
  ``weights_only`` e con torch 2.10 rifiuta i suoi stessi checkpoint.
- ``torch.hub.load_state_dict_from_url`` (lo chiama il repo remoto di
  demucs): stessa firma e ``weights_only=False`` di default in entrambe.
  Uguale, ma fa il pickle completo e verifica l'hash solo al download, non
  a ogni avvio: per questo ``get_demucs_model`` lo sostituisce con
  ``download_url_to_file`` + ``load_checkpoint``.
- ``torchaudio.functional.resample`` con ``sinc_interp_kaiser``, hook di
  forward, ``torch.backends.mps``, ``set_grad_enabled``/``inference_mode``,
  ``from_numpy`` con numpy 1 e 2: identici, lo provano i test ``compat``.

Pesi demucs e sicurezza: un checkpoint demucs e' un pickle con dentro la
classe del modello (``demucs.htdemucs.HTDemucs``), il segmento come
``fractions.Fraction`` e qualche scalare numpy, quindi il caricamento
"solo tensori" di torch lo rifiuta. Dalla 2.5 lo si ammette con un elenco
chiuso di classi (``DEMUCS_SAFE_GLOBALS``) e il resto resta vietato; la
2.2.2 non ha modo di estendere l'elenco e carica il pickle completo. In
entrambi i casi si carica solo dopo aver verificato l'hash SHA-256 che il
nome del file porta con se' (``<firma>-<hash>.th``, convenzione torch hub).
"""

from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path
from typing import Any, ContextManager

# Nomi come compaiono nel pickle dei checkpoint htdemucs (letti con
# torch.serialization.get_unsafe_globals_in_checkpoint sui quattro pesi di
# htdemucs_ft). "numpy.core" e' il nome che numpy 1 ha scritto nel file:
# con numpy 2 il modulo si chiama numpy._core, va abbinato per nome.
# Float64DType non compare nel file: e' il tipo che numpy.dtype("f8")
# restituisce quando il pickle lo ricostruisce (metriche di training).
DEMUCS_SAFE_GLOBALS = (
    "demucs.htdemucs.HTDemucs",
    "fractions.Fraction",
    "numpy.dtype",
    "numpy.dtypes.Float64DType",
    "numpy.core.multiarray.scalar",
)

_HASH_IN_NAME = re.compile(r"-([0-9a-f]{8,64})\.[A-Za-z0-9]+$")
_READ_CHUNK = 1 << 20


class CheckpointError(RuntimeError):
    """Pesi da non caricare: hash assente, diverso o file illeggibile."""


def torch_version() -> tuple[int, int]:
    """(maggiore, minore) del torch installato, senza suffissi locali (+cpu)."""
    import torch

    major, minor = torch.__version__.split("+", 1)[0].split(".")[:2]
    return int(major), int(minor)


def has_weights_only_allowlist() -> bool:
    """True se torch sa caricare pesi "solo dati" con classi ammesse in piu'."""
    import torch

    return hasattr(torch.serialization, "safe_globals")


def expected_hash_prefix(path: Path) -> str:
    """Prefisso SHA-256 scritto nel nome del checkpoint (``sig-<hash>.th``)."""
    match = _HASH_IN_NAME.search(path.name)
    if match is None:
        raise CheckpointError(
            f"{path.name}: il nome non contiene l'hash dei pesi, impossibile verificarli"
        )
    return match.group(1)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checkpoint(path: Path) -> None:
    """Solleva CheckpointError se il file non e' quello che il nome promette."""
    expected = expected_hash_prefix(path)
    try:
        actual = sha256_of(path)
    except OSError as exc:
        raise CheckpointError(f"{path.name}: pesi illeggibili ({exc})") from exc
    if not actual.startswith(expected):
        raise CheckpointError(
            f"{path.name}: hash {actual[: len(expected)]} invece di {expected}: "
            "file danneggiato o alterato, va riscaricato"
        )


def _resolve_global(dotted: str) -> Any:
    module_name, _, attribute = dotted.rpartition(".")
    if module_name == "numpy.core.multiarray":
        # numpy 2 ha rinominato numpy.core in numpy._core e l'alias vecchio
        # avvisa a ogni accesso: si prende il modulo vero quando c'e'.
        try:
            module = importlib.import_module("numpy._core.multiarray")
        except ImportError:
            module = importlib.import_module(module_name)
        return getattr(module, attribute)
    return getattr(importlib.import_module(module_name), attribute)


def _allowlist(names: tuple[str, ...]) -> list[Any]:
    """Classi ammesse col nome scritto nel pickle e, se diverso, con
    quello attuale (un file salvato con numpy 2 usa numpy._core)."""
    entries: list[Any] = []
    for dotted in names:
        obj = _resolve_global(dotted)
        actual = f"{getattr(obj, '__module__', '')}.{getattr(obj, '__name__', '')}"
        entries.append(obj)
        if actual != dotted:
            entries.append((obj, dotted))
    return entries


def _safe_globals(names: tuple[str, ...]) -> ContextManager[Any]:
    import torch

    # context manager e non add_safe_globals: l'elenco vale solo per
    # questo caricamento, nessuno stato globale (§11 regola 6)
    return torch.serialization.safe_globals(_allowlist(names))


def load_checkpoint(path: Path, allowed: tuple[str, ...] = DEMUCS_SAFE_GLOBALS) -> Any:
    """Verifica l'hash, poi carica i pesi su CPU nel modo piu' sicuro che
    il torch installato consente (vedi la docstring del modulo)."""
    import torch

    verify_checkpoint(path)
    if has_weights_only_allowlist():
        with _safe_globals(allowed):
            return torch.load(path, map_location="cpu", weights_only=True)
    # torch 2.2.2: l'elenco non si estende e i pesi demucs contengono
    # classi Python. Pickle completo, ma solo di un file con l'hash giusto.
    return torch.load(path, map_location="cpu", weights_only=False)


class VerifiedRemoteRepo:
    """Il repo remoto di demucs (``demucs.repo.RemoteRepo``) con i pesi
    caricati da ``load_checkpoint`` invece che dal pickle completo di
    ``torch.hub.load_state_dict_from_url``. Stessa cartella e stessi nomi
    di torch hub: i pesi gia' scaricati si riusano."""

    def __init__(self, urls: dict[str, str], checkpoints: Path) -> None:
        self._urls = urls
        self._checkpoints = checkpoints

    def has_model(self, sig: str) -> bool:
        return sig in self._urls

    def get_model(self, sig: str) -> Any:
        import torch
        from demucs.repo import ModelLoadingError
        from demucs.states import load_model

        if sig not in self._urls:
            raise ModelLoadingError(f"nessun modello demucs con firma {sig}")
        url = self._urls[sig]
        path = self._checkpoints / url.rsplit("/", 1)[-1]
        if path.is_file():
            try:
                return load_model(load_checkpoint(path))
            except CheckpointError:
                # danneggiato sul disco: si riscarica, non si carica (§9.2)
                path.unlink()
        self._checkpoints.mkdir(parents=True, exist_ok=True)
        # scrive su un temporaneo e rinomina solo se l'hash torna
        torch.hub.download_url_to_file(url, str(path), hash_prefix=expected_hash_prefix(path))
        return load_model(load_checkpoint(path))


def get_demucs_model(name: str) -> Any:
    """``demucs.pretrained.get_model(name)`` per i modelli ufficiali, con
    ogni checkpoint verificato e caricato da ``load_checkpoint``. I pesi
    stanno in ``<torch.hub.get_dir()>/checkpoints``, come prima."""
    import torch
    from demucs import pretrained
    from demucs.repo import AnyModelRepo, BagOnlyRepo

    # funzione privata di demucs, stabile perche' demucs e' fissato a 4.0.1
    urls = pretrained._parse_remote_files(pretrained.REMOTE_ROOT / "files.txt")
    model_repo = VerifiedRemoteRepo(urls, Path(torch.hub.get_dir()) / "checkpoints")
    bag_repo = BagOnlyRepo(pretrained.REMOTE_ROOT, model_repo)
    model = AnyModelRepo(model_repo, bag_repo).get_model(name)
    model.eval()
    return model
