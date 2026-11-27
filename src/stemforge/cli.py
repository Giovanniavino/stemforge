"""CLI headless: stessa pipeline dell'app (BUILD_SPEC §3, §12-M1).

`stemforge brano.mp3 --stems vocals,drums,bass,other [--lang en]`

Un file che fallisce in un batch non ferma gli altri (§10.1); i backend
si caricano una volta sola per l'intero batch (§6.1). I testi escono
nella lingua di --lang, altrimenti in quella del sistema (§8.6): la CLI
la passa al motore con STEMFORGE_LOCALE, come fa il bridge dell'app.
Il traceback va nel log, mai sullo schermo (§10.1 regola 2).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from stemforge.engine import calibrate
from stemforge.engine.planner import estimate_pass_seconds, estimate_seconds, plan
from stemforge.model.job import DEVICES, FORMATS, QUALITIES, SeparationJob
from stemforge.model.stem import StemKind
from stemforge.worker import i18n, protocol
from stemforge.worker.i18n import t
from stemforge.worker.messages import user_message
from stemforge.worker.pipeline import BackendCache, run_job
from stemforge.worker.planning import ESTIMATE_MARGIN

log = logging.getLogger(__name__)


def _parse_stems(raw: str) -> tuple[StemKind, ...]:
    kinds: list[StemKind] = []
    for token in raw.split(","):
        token = token.strip().lower()
        if not token:
            continue
        try:
            kinds.append(StemKind(token))
        except ValueError:
            valid = ", ".join(k.value for k in StemKind)
            raise SystemExit(t("cli.unknown_stem", stem=token, valid=valid)) from None
    if not kinds:
        raise SystemExit(t("cli.no_stems"))
    return tuple(kinds)


def _default_out_dir() -> Path:
    return Path.home() / "Music" / "StemForge"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stemforge",
        description="Separa un brano negli stem scelti e li scrive come WAV/FLAC.",
    )
    parser.add_argument("sources", nargs="+", type=Path, metavar="FILE")
    parser.add_argument(
        "--stems",
        default="vocals,drums,bass,other",
        help="lista separata da virgole (default: vocals,drums,bass,other)",
    )
    parser.add_argument("--quality", choices=QUALITIES, default="best")
    parser.add_argument("--format", dest="fmt", choices=FORMATS, default="wav")
    parser.add_argument("--device", choices=DEVICES, default="auto")
    parser.add_argument("--out", type=Path, default=None, help="cartella base di output")
    parser.add_argument("--dereverb", action="store_true", help="voce asciutta + vocals_wet")
    parser.add_argument(
        "--lang", choices=i18n.LOCALES, default=None,
        help="lingua dei messaggi, it o en (default: quella del sistema)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra il piano e la stima, non separa"
    )
    return parser


def apply_language(lang: str | None) -> str:
    """Fissa la lingua del processo per il motore (§8.6) e la restituisce."""
    chosen = lang if lang is not None else i18n.system_locale()
    os.environ[i18n.LOCALE_ENV] = chosen
    return chosen


def _job_for(args: argparse.Namespace, source: Path) -> SeparationJob:
    return SeparationJob(
        source=source,
        wanted=_parse_stems(args.stems),
        quality=args.quality,
        out_dir=args.out if args.out is not None else _default_out_dir(),
        fmt=args.fmt,
        device=args.device,
        dereverb_vocals=args.dereverb,
    )


def _print_plan(job: SeparationJob, duration_s: float | None) -> None:
    plan_ = plan(job)
    rates = calibrate.load_rates()
    print(t("cli.plan_model", model=plan_.first_stage_model))
    for index, p in enumerate(plan_.passes, start=1):
        line = t("cli.plan_pass", index=index, label=t(f"phase.{p.backend}"),
                 backend=p.backend, stems=", ".join(p.needed))
        if duration_s is not None:
            seconds = estimate_pass_seconds(p, duration_s, rates, job.quality)
            line += f" (~{seconds * ESTIMATE_MARGIN:.0f} s)"
        print(line)
    if duration_s is not None:
        total = estimate_seconds(plan_, duration_s, rates) * ESTIMATE_MARGIN
        print(t("cli.plan_total", seconds=f"{total:.0f}", count=len(plan_.passes)))


def _emit_console(message: protocol.Message) -> None:
    if isinstance(message, protocol.Phase):
        print(f"[{message.pass_index}/{message.pass_count}] {message.label}")
    elif isinstance(message, protocol.Progress):
        print(f"\r  {message.value * 100:5.1f}%", end="", flush=True)
    elif isinstance(message, protocol.Warning_):
        print("\n" + t("cli.warning", message=message.message))
    elif isinstance(message, protocol.Done):
        print("\n" + t("cli.done", path=message.out_dir))


def _run_one(args: argparse.Namespace, source: Path, backends: BackendCache) -> str | None:
    """Un file del batch; restituisce il messaggio per il riepilogo, se fallisce."""
    job = _job_for(args, source)
    if args.dry_run:
        print(f"{source.name}:")
        _print_plan(job, _probe_duration(source))
        return None
    print(f"== {source.name} ==")
    try:
        run_job(job, _emit_console, backends=backends)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # un file non ferma il batch (§10.1)
        log.exception("job fallito su %s", source)
        message = user_message(exc)
        print("\n" + t("cli.error", name=source.name, message=message), file=sys.stderr)
        return f"{source.name}: {message}"
    return None


def main(argv: list[str] | None = None) -> int:
    from stemforge.engine.device import prepare_runtime_env

    prepare_runtime_env()  # certificati HTTPS e ripiego MPS, prima di torch
    args = build_parser().parse_args(argv)
    apply_language(args.lang)
    failures: list[str] = []
    backends: BackendCache = {}
    for source in args.sources:
        if not source.exists():
            failures.append(t("err.not_found", name=str(source)))
            continue
        try:
            failure = _run_one(args, source, backends)
        except KeyboardInterrupt:
            print("\n" + t("cli.cancelled"))
            return 130
        if failure is not None:
            failures.append(failure)
    if failures:
        print("\n" + t("cli.summary"), file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


def _probe_duration(source: Path) -> float | None:
    from stemforge.engine.audio_io import probe_duration

    return probe_duration(source)


if __name__ == "__main__":
    sys.exit(main())
