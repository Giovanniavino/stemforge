"""Entry point del processo figlio (BUILD_SPEC D2).

Job su stdin (una riga JSON), messaggi JSON-lines su stdout. La logica
vive in pipeline.py: qui c'è solo il confine del processo — parsing,
raccolta degli errori, codici di uscita — e la modalità `--prepare`
del primo avvio (§9.4).
"""

from __future__ import annotations

import json
import sys
import traceback

from stemforge.engine import audio_io, calibrate
from stemforge.engine.contract import BackendUnavailable, CancelledError
from stemforge.engine.device import resolve_device
from stemforge.model.job import SeparationJob
from stemforge.worker import protocol
from stemforge.worker.pipeline import run_job

__all__ = ["run_job", "main"]


def _prepare() -> int:
    """Primo avvio (§9.4): scarica i pesi e calibra, emettendo progresso.

    Vive nel worker e non nella UI perché la UI non importa engine
    (§8.5): il bridge lancia `--prepare` con lo stesso QProcess dei job.
    """
    from stemforge.engine.demucs4 import ensure_models

    def emit(message: protocol.Message) -> None:
        protocol.write_message(sys.stdout, message)

    models = ("htdemucs_ft", "htdemucs_6s")
    try:
        for index, name in enumerate(models, start=1):
            emit(protocol.Phase(
                label=f"Scarico il modello {name}",
                pass_index=index, pass_count=len(models) + 1,
            ))
            ensure_models(name)
        emit(protocol.Phase(
            label="Misuro la velocità di questo Mac per darti stime oneste",
            pass_index=len(models) + 1, pass_count=len(models) + 1,
        ))
        device = resolve_device("auto")
        calibrate.first_run_calibration(device)
    except BackendUnavailable as exc:
        emit(protocol.Error(message=str(exc), detail=traceback.format_exc()))
        return 1
    marker = calibrate.calibration_path().parent / "prepared.json"
    marker.write_text(json.dumps({"models": list(models)}), encoding="utf-8")
    emit(protocol.Done(out_dir="", manifest=""))
    return 0


def _user_message(exc: Exception) -> str:
    """Ogni errore dice cosa fare (§10.1); il traceback va nel log."""
    if isinstance(exc, (audio_io.UnsupportedFormatError, audio_io.TooLongError)):
        return str(exc)
    if isinstance(exc, MemoryError):
        return (
            "Memoria insufficiente: chiudi altre applicazioni o riprova "
            "con il preset Veloce."
        )
    if isinstance(exc, (RuntimeError, OSError)) and str(exc):
        return str(exc)
    return "Elaborazione non riuscita. Riprova; se succede ancora, guarda il log."


def main() -> int:
    """Entry point del figlio: job su stdin, JSON-lines su stdout (D2)."""
    if "--prepare" in sys.argv:
        return _prepare()
    line = sys.stdin.readline()
    try:
        job = SeparationJob.from_json(line)
    except (ValueError, KeyError) as exc:
        protocol.write_message(
            sys.stdout,
            protocol.Error(message="Richiesta non valida.", detail=repr(exc)),
        )
        return 2

    def emit(message: protocol.Message) -> None:
        protocol.write_message(sys.stdout, message)

    try:
        run_job(job, emit)
    except CancelledError:
        return 130
    except BackendUnavailable as exc:
        emit(protocol.Error(message=str(exc), detail=traceback.format_exc()))
        return 1
    except Exception as exc:  # confine del processo: qui si raccoglie tutto
        emit(protocol.Error(
            message=_user_message(exc),
            detail=traceback.format_exc(),
        ))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
