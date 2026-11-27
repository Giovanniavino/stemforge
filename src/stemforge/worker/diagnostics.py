"""Esporta diagnostica: uno zip che l'utente salva e manda se vuole (§9.9).

Niente telemetria (§0): lo zip si crea solo quando l'utente lo chiede,
nella cartella che sceglie, e nessuno lo spedisce al posto suo. Dentro:
il log, la versione, il sistema, l'esito di `--selftest --offline` e i
verdetti dei dispositivi (device.json) con la calibrazione. Il log
contiene i nomi dei brani elaborati: il LEGGIMI dello zip lo dice.

Il collaudo gira in un PROCESSO A PARTE (lo stesso comando del pacchetto,
§10.5): così il processo dell'interfaccia non carica torch (§8.5) e il
collaudo non tocca la calibrazione vera (usa la sua, temporanea).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from stemforge import __version__
from stemforge.engine import device, paths
from stemforge.worker import i18n
from stemforge.worker.i18n import t
from stemforge.worker.launch import selftest_command

log = logging.getLogger(__name__)

# Il collaudo offline decodifica qualche secondo di audio e costruisce
# l'interfaccia: un minuto su un Mac del 2012, dieci sono già un guasto.
SELFTEST_TIMEOUT_S = 10 * 60
_OUTPUT_TAIL_CHARS = 8000
_LOG_GLOB = "stemforge.log*"  # il file corrente e le rotazioni .1 .2 .3 (§10.1)

SelftestRunner = Callable[[Path], "dict[str, object]"]


def run_offline_selftest(workdir: Path) -> dict[str, object]:
    """`--selftest --offline` in un processo figlio; mai un'eccezione.

    Un collaudo che non parte è proprio ciò che la diagnostica deve
    riportare: l'errore finisce nel report invece di fermare l'export.
    """
    report = workdir / "selftest.json"
    try:
        proc = subprocess.run(
            selftest_command(report, offline=True),
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=SELFTEST_TIMEOUT_S,
            # dall'app a finestra su Windows: niente console che lampeggia
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("collaudo per la diagnostica non avviato", exc_info=True)
        return {"ok": False, "error": f"collaudo non avviato: {exc!r}"}
    output = (proc.stdout + proc.stderr)[-_OUTPUT_TAIL_CHARS:]
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "exit": proc.returncode, "output": output,
                "error": f"report del collaudo assente: {exc!r}"}
    if not isinstance(data, dict):
        return {"ok": False, "exit": proc.returncode, "output": output,
                "error": "report del collaudo malformato"}
    data.update(exit=proc.returncode, output=output)
    return data


def system_info(now: datetime) -> dict[str, object]:
    return {
        "stemforge": __version__,
        "created": now.isoformat(timespec="seconds"),
        **device.platform_info(),
        "cpu_count": os.cpu_count(),
        "available_memory_bytes": device.available_memory_bytes(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "locale": i18n.current_locale(),
    }


def _state_files() -> dict[str, Path]:
    """I file di stato della macchina: verdetti (D8) e calibrazione (§8.2.1)."""
    calibration = paths.calibration_path()
    return {
        "device.json": device.verdict_path(),
        "calibration.json": calibration,
        "prepared.json": calibration.parent / "prepared.json",
    }


def _add_file(archive: zipfile.ZipFile, name: str, path: Path, missing: list[str]) -> None:
    # read_bytes e non archive.write: il log può crescere mentre lo si
    # legge (l'app lo tiene aperto), e un file che sparisce non è un guasto
    try:
        archive.writestr(name, path.read_bytes())
    except OSError as exc:
        missing.append(f"{name}: {exc.strerror or exc!r}")


def _free_name(dest_dir: Path, stem: str) -> Path:
    candidate = dest_dir / f"{stem}.zip"
    counter = 2
    while candidate.exists():
        candidate = dest_dir / f"{stem} ({counter}).zip"
        counter += 1
    return candidate


def _write_zip(target: Path, selftest: dict[str, object], logs: Path, now: datetime) -> None:
    missing: list[str] = []
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("LEGGIMI.txt", t("diag.readme", version=__version__))
        archive.writestr("sistema.json", json.dumps(system_info(now), indent=2))
        archive.writestr("selftest.json", json.dumps(selftest, indent=2, ensure_ascii=False))
        for name, path in _state_files().items():
            if path.is_file():
                _add_file(archive, name, path, missing)
        for path in sorted(logs.glob(_LOG_GLOB)) if logs.is_dir() else []:
            _add_file(archive, f"log/{path.name}", path, missing)
        if missing:
            archive.writestr("non_letti.txt", "\n".join(missing))


def export_diagnostics(
    dest_dir: Path,
    run_selftest: SelftestRunner = run_offline_selftest,
    log_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Crea lo zip della diagnostica in `dest_dir` e ne restituisce il percorso.

    Non sovrascrive mai: un secondo export nello stesso secondo prende
    " (2)". Lo zip si scrive accanto con un nome provvisorio e si rinomina
    alla fine, così un errore non lascia uno zip a metà col nome giusto.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    now = now if now is not None else datetime.now()
    with tempfile.TemporaryDirectory(prefix="stemforge-diag-", ignore_cleanup_errors=True) as tmp:
        selftest = run_selftest(Path(tmp))
    target = _free_name(dest_dir, f"StemForge-diagnostica-{now:%Y%m%d-%H%M%S}")
    partial = target.with_name(target.name + ".part")
    try:
        _write_zip(partial, selftest, log_dir if log_dir is not None else paths.log_dir(), now)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target
