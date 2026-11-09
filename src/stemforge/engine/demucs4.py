"""Backend Demucs v4: htdemucs_ft (bag di 4) e htdemucs_6s.

BUILD_SPEC §5.1, §5.1.1. Scelte non ovvie, con la ragione:

- NON si reimplementa la segmentazione/overlap di demucs: si usa la sua
  `apply_model` ufficiale, così la numerica resta identica a quella
  convalidata dal progetto demucs. Progresso e annullo si ottengono con
  un forward pre-hook sui sotto-modelli: ogni forward è un segmento,
  quindi il conteggio è esatto e `should_cancel` viene consultato
  esattamente fra un segmento e l'altro (§5.5).
- L'esecuzione parziale (§5.1.1) costruisce un BagOfModels ridotto con i
  PESI REALI letti dal checkpoint: se un giorno i pesi non fossero
  one-hot, la selezione includerebbe automaticamente ogni sotto-modello
  con peso non nullo sulle sorgenti richieste, restando identica
  all'insieme completo per costruzione.
- La normalizzazione (media/std del mix) sta fuori da apply_model, come
  in demucs/separate.py: va replicata qui e disfatta in uscita.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from stemforge.engine import paths
from stemforge.engine.contract import BackendUnavailable, CancelledError, Quality
from stemforge.model.stem import StemKind

if TYPE_CHECKING:
    from torch import Tensor

_EPS = 1e-8


def models_dir() -> Path:
    """Dove vivono i pesi (§9.2). Sovrascrivibile per i test."""
    return paths.models_dir()


def _load_model(model_name: str):
    import torch

    target = models_dir()
    target.mkdir(parents=True, exist_ok=True)
    # demucs scarica nel torch hub e verifica gli hash incorporati nei
    # nomi dei checkpoint del remote ufficiale (§9.2).
    torch.hub.set_dir(str(target))
    from demucs.pretrained import get_model

    try:
        model = get_model(model_name)
    except Exception as exc:  # rete giù, hash errato, disco pieno...
        raise BackendUnavailable(
            f"Modello {model_name} non disponibile: {exc}. "
            "Serve la connessione una sola volta per scaricarlo."
        ) from exc
    model.eval()
    return model


def ensure_models(model_name: str) -> None:
    """Scarica (se serve) e valida i pesi. Usato dal primo avvio (§9.4)."""
    _load_model(model_name)


class Demucs4Backend:
    """Un'istanza per modello di primo stadio; i pesi si caricano una
    volta sola e restano vivi per tutto il job, batch compreso (§6.1)."""

    name = "demucs4"
    samplerate = 44100

    def __init__(self, model_name: str, device: str, quality: Quality) -> None:
        self.model_name = model_name
        self.device = device
        self.quality = quality
        self._model = _load_model(model_name)
        self.sources: tuple[StemKind, ...] = tuple(
            StemKind(s) for s in self._model.sources
        )
        self.provides: frozenset[StemKind] = frozenset(self.sources)
        self._is_bag = hasattr(self._model, "models")
        self._prepare_device()

    def _prepare_device(self) -> None:
        import torch

        submodels = self._model.models if self._is_bag else [self._model]
        for sub in submodels:
            sub.to(self.device)
            if self.quality.half and self.device == "cuda":
                sub.half()
        torch.set_grad_enabled(False)

    def _select(self, wanted: frozenset[StemKind]):
        """Sotto-insieme del bag che copre le sorgenti richieste (§5.1.1)."""
        from demucs.apply import BagOfModels

        if not self._is_bag:
            return self._model
        weights = self._model.weights  # [n_models][n_sources]
        idx = [i for i, s in enumerate(self.sources) if s in wanted]
        keep = [
            m
            for m, w in enumerate(weights)
            if any(abs(w[i]) > _EPS for i in idx)
        ]
        if len(keep) == len(self._model.models):
            return self._model
        return BagOfModels(
            [self._model.models[m] for m in keep],
            weights=[weights[m] for m in keep],
            segment=getattr(self._model, "segment", None),
        )

    def submodel_count(self, wanted: frozenset[StemKind]) -> int:
        model = self._select(wanted)
        return len(model.models) if hasattr(model, "models") else 1

    def separate(
        self,
        audio: "Tensor",
        wanted: frozenset[StemKind],
        on_progress: Callable[[float], None],
        should_cancel: Callable[[], bool],
    ) -> dict[StemKind, "Tensor"]:
        import torch
        from demucs.apply import apply_model

        model = self._select(wanted)
        submodels = model.models if hasattr(model, "models") else [model]
        segment_calls = self._expected_calls(audio.shape[-1], submodels)
        counter = {"done": 0}
        hooks = [
            sub.register_forward_pre_hook(
                self._make_hook(counter, segment_calls, on_progress, should_cancel)
            )
            for sub in submodels
        ]
        try:
            ref = audio.mean(0)
            mean, std = ref.mean(), ref.std()
            norm = (audio - mean) / (std + _EPS)
            if self.quality.half and self.device == "cuda":
                norm = norm.half()
            out = apply_model(
                model,
                norm[None],
                shifts=self.quality.shifts,
                split=True,
                overlap=self.quality.overlap,
                device=self.device,
                progress=False,
            )[0]
            out = out.to(torch.float32).cpu() * (std + _EPS) + mean
        finally:
            for hook in hooks:
                hook.remove()
        return {
            kind: out[i] for i, kind in enumerate(self.sources) if kind in wanted
        }

    def _expected_calls(self, length: int, submodels: list) -> int:
        stride = int((1.0 - self.quality.overlap) * self.samplerate * _segment_s(submodels[0]))
        per_model = max(1, -(-length // max(1, stride)))  # ceil
        shifts = max(1, self.quality.shifts)
        return per_model * shifts * len(submodels)

    @staticmethod
    def _make_hook(
        counter: dict[str, int],
        total: int,
        on_progress: Callable[[float], None],
        should_cancel: Callable[[], bool],
    ):
        def hook(_module, _inputs):
            if should_cancel():
                raise CancelledError("annullato dall'utente")
            counter["done"] += 1
            # Mai oltre 1.0 anche se la stima dei segmenti fosse per
            # difetto: on_progress deve restare monotòno in [0, 1] (§5.5).
            on_progress(min(1.0, counter["done"] / max(1, total)))

        return hook


def _segment_s(model) -> float:
    segment = getattr(model, "segment", None)
    return float(segment) if segment else 7.8
