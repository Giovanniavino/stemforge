"""Entry point del processo figlio (BUILD_SPEC D2).

Job su stdin (una riga JSON), messaggi JSON-lines su stdout. La logica
vive in pipeline.py: qui c'è solo il confine del processo — parsing,
raccolta degli errori, codici di uscita — e la modalità `--prepare`
del primo avvio (§9.4).

I testi per l'utente escono già nella lingua di STEMFORGE_LOCALE, che
imposta chi lancia il processo (§8.6); il traceback va solo in
`detail`, per il log (§10.1 regola 2).
"""

from __future__ import annotations

import json
import sys
import traceback

from stemforge.engine import calibrate
from stemforge.engine.contract import CancelledError
from stemforge.engine.device import prepare_runtime_env
from stemforge.model.job import SeparationJob
from stemforge.worker import protocol
from stemforge.worker.i18n import t
from stemforge.worker.messages import prepare_message, user_message
from stemforge.worker.pipeline import run_job

__all__ = ["run_job", "main"]

_PREPARE_MODELS = ("htdemucs_ft", "htdemucs_6s")


def _emit(message: protocol.Message) -> None:
    protocol.write_message(sys.stdout, message)


def _prepare_steps() -> None:
    from stemforge.engine.demucs4 import ensure_models

    count = len(_PREPARE_MODELS) + 1
    for index, name in enumerate(_PREPARE_MODELS, start=1):
        _emit(protocol.Phase(label=t("phase.download", name=name), pass_index=index,
                             pass_count=count))
        ensure_models(name)
    _emit(protocol.Phase(label=t("phase.calibrate"), pass_index=count, pass_count=count))
    # qui si verifica anche l'acceleratore (MPS, CUDA) contro la CPU (D8)
    device = calibrate.resolve_job_device("auto")
    calibrate.first_run_calibration(device)
    marker = calibrate.calibration_path().parent / "prepared.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"models": list(_PREPARE_MODELS)}), encoding="utf-8")


def _prepare() -> int:
    """Primo avvio (§9.4): scarica i pesi e calibra, emettendo progresso.

    Vive nel worker e non nella UI perché la UI non importa engine
    (§8.5): il bridge lancia `--prepare` con lo stesso QProcess dei job.
    """
    try:
        _prepare_steps()
    except Exception as exc:
        # qualunque cosa vada storta qui deve arrivare all'utente come
        # messaggio, mai come processo morto in silenzio (§10.1)
        _emit(protocol.Error(message=prepare_message(exc), detail=traceback.format_exc()))
        return 1
    _emit(protocol.Done(out_dir="", manifest=""))
    return 0


def main() -> int:
    """Entry point del figlio: job su stdin, JSON-lines su stdout (D2)."""
    prepare_runtime_env()  # certificati HTTPS e ripiego MPS, prima di torch
    if "--prepare" in sys.argv:
        return _prepare()
    line = sys.stdin.readline()
    try:
        job = SeparationJob.from_json(line)
    except (ValueError, KeyError, TypeError) as exc:
        _emit(protocol.Error(message=t("err.invalid_request"), detail=repr(exc)))
        return 2
    try:
        run_job(job, _emit)
    except CancelledError:
        return 130
    except Exception as exc:  # confine del processo: qui si raccoglie tutto
        _emit(protocol.Error(message=user_message(exc), detail=traceback.format_exc()))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
