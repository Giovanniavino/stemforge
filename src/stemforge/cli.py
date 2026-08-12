"""CLI headless: stessa pipeline dell'app (BUILD_SPEC §3, §12-M1).

`stemforge brano.mp3 --stems vocals,drums,bass,other`

Un file che fallisce in un batch non ferma gli altri (§10.1); i backend
si caricano una volta sola per l'intero batch (§6.1).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stemforge.engine import calibrate
from stemforge.engine.planner import estimate_pass_seconds, estimate_seconds, plan
from stemforge.model.job import DEVICES, FORMATS, QUALITIES, SeparationJob
from stemforge.model.stem import StemKind
from stemforge.worker import protocol
from stemforge.worker.pipeline import BackendCache, run_job

# Il margine di sovrastima della stima mostrata (§8.2.1).
ESTIMATE_MARGIN = 1.15


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
            raise SystemExit(f"stem sconosciuto: {token!r}. Validi: {valid}")
    if not kinds:
        raise SystemExit("nessuno stem richiesto")
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
        "--dry-run", action="store_true", help="mostra il piano e la stima, non separa"
    )
    return parser


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
    print(f"modello 1° stadio: {plan_.first_stage_model}")
    for index, p in enumerate(plan_.passes, start=1):
        line = f"  passata {index}: {p.label} [{p.backend}] -> {', '.join(p.needed)}"
        if duration_s is not None:
            seconds = estimate_pass_seconds(p, duration_s, rates, job.quality)
            line += f" (~{seconds * ESTIMATE_MARGIN:.0f} s)"
        print(line)
    if duration_s is not None:
        total = estimate_seconds(plan_, duration_s, rates) * ESTIMATE_MARGIN
        unit = "passata" if len(plan_.passes) == 1 else "passate"
        print(f"stima totale: ~{total:.0f} s · {len(plan_.passes)} {unit}")


def _emit_console(message: protocol.Message) -> None:
    if isinstance(message, protocol.Phase):
        print(f"[{message.pass_index}/{message.pass_count}] {message.label}")
    elif isinstance(message, protocol.Progress):
        print(f"\r  {message.value * 100:5.1f}%", end="", flush=True)
    elif isinstance(message, protocol.Warning_):
        print(f"\navviso: {message.message}")
    elif isinstance(message, protocol.Done):
        print(f"\nfatto: {message.out_dir}")


def main(argv: list[str] | None = None) -> int:
    from stemforge.engine.device import ensure_ca_bundle

    ensure_ca_bundle()  # prima di qualsiasi download (pesi via HTTPS)
    args = build_parser().parse_args(argv)
    failures: list[str] = []
    backends: BackendCache = {}
    for source in args.sources:
        if not source.exists():
            failures.append(f"{source}: file non trovato")
            continue
        job = _job_for(args, source)
        if args.dry_run:
            duration = _probe_duration(source)
            print(f"{source.name}:")
            _print_plan(job, duration)
            continue
        print(f"== {source.name} ==")
        try:
            run_job(job, _emit_console, backends=backends)
        except KeyboardInterrupt:
            print("\nannullato")
            return 130
        except Exception as exc:  # un file non ferma il batch (§10.1)
            failures.append(f"{source.name}: {exc}")
            print(f"\nerrore su {source.name}: {exc}", file=sys.stderr)
    if failures:
        print("\nriepilogo errori:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


def _probe_duration(source: Path) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(str(source))
        return info.frames / info.samplerate
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
