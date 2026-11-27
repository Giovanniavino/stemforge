"""Collaudo dell'installer Windows così come lo riceve l'utente (§9.6, §9.7).

    python packaging/ci/verify_windows_installer.py <setup.exe> <report.json>
        [--matrix] [--dir CARTELLA] [--skip-selftest] [--skip-open-with]

Per ogni cartella di installazione: installa in silenzio (per utente,
senza amministratore), controlla menu Start, "Apri con" nel registro e
che le associazioni predefinite NON siano cambiate, collauda l'app
INSTALLATA con --selftest, la apre come la apre "Apri con" su un wav,
poi la disinstalla in silenzio e verifica che sia sparita davvero e che
i dati dell'utente (%LOCALAPPDATA%\\StemForge) siano rimasti.

--matrix prova cartella predefinita, cartella con spazi e accenti e
percorso oltre 200 caratteri (§9.7): se l'app non ci sta sotto MAX_PATH
l'installer deve rifiutarlo pulito, e il collaudo completo si ripete
nella cartella più lunga che accetta. Senza --matrix, solo una cartella
temporanea (o quella di --dir). Il riepilogo va in <report.json>, i
--selftest accanto, uno per caso.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows"))
import windows_integration as wi  # noqa: E402

_INSTALL_TIMEOUT_S = 15 * 60
_UNINSTALL_WAIT_S = 180
_OPEN_WITH_ALIVE_S = 10
_LONG_PATH_MIN_CHARS = 200
_DESKTOP_TASK = "desktopicon"  # il nome del compito in [Tasks] di stemforge.iss
# (nome, cartella chiesta con /DIR o None per la predefinita, icona sul desktop scelta)
Case = tuple[str, Path | None, bool]


def _run_setup(setup: Path, target: Path | None, log: Path, desktop: bool = False) -> int:
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", f"/LOG={log}"]
    if target is not None:
        command.append(f"/DIR={target}")
    if desktop:
        command.append(f"/TASKS={_DESKTOP_TASK}")
    return subprocess.run(command, timeout=_INSTALL_TIMEOUT_S).returncode


def _install(setup: Path, target: Path | None, log: Path, desktop: bool) -> Path:
    code = _run_setup(setup, target, log, desktop)
    installed = wi.installed_dir()
    if code != 0 or installed is None or not (installed / wi.APP_EXE).is_file():
        print(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "nessun log")
        raise AssertionError(f"installazione fallita (uscita {code}, cartella {installed})")
    if target is not None and os.path.normcase(installed) != os.path.normcase(target):
        raise AssertionError(f"installato in {installed} invece di {target}")
    return installed


def _uninstall() -> None:
    command = wi.uninstall_command()
    subprocess.run([*command, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    # il disinstallatore si copia in una cartella temporanea e ritorna subito
    deadline = time.monotonic() + _UNINSTALL_WAIT_S
    while time.monotonic() < deadline:
        if wi.installed_dir() is None and not Path(command[0]).exists():
            return
        time.sleep(1)
    raise AssertionError("disinstallazione non conclusa entro il tempo massimo")


def _choices(associations: dict[str, dict]) -> dict[str, dict]:
    return {ext: {k: v for k, v in values.items() if k != "hkcu_key"} for ext, values in associations.items()}


def _check_installed(app_dir: Path, associations: dict[str, dict[str, str | None]], desktop: bool) -> list[str]:
    exe = app_dir / wi.APP_EXE
    lines = [wi.check_start_menu(exe), wi.check_desktop_icon(exe, desktop), wi.check_open_with(exe)]
    # da installata la chiave .ext in HKCU può esserci in più (OpenWithProgids):
    # conta che il predefinito e la UserChoice non cambino
    after = _choices(wi.default_associations())
    associations = _choices(associations)
    if after != associations:
        raise AssertionError(f"associazioni predefinite cambiate:\nprima {associations}\ndopo  {after}")
    lines.append("associazioni predefinite invariate")
    return lines


def _check_removed(app_dir: Path, associations: dict, data_before: tuple[int, int] | None) -> list[str]:
    leftovers = sorted(str(p) for p in app_dir.rglob("*")) if app_dir.exists() else []
    if leftovers:
        raise AssertionError(f"file rimasti dopo la disinstallazione: {leftovers[:20]}")
    lines = [wi.check_integration_removed()]
    after = wi.default_associations()
    if after != associations:
        raise AssertionError(f"registro delle estensioni cambiato dalla disinstallazione:\nprima {associations}\ndopo  {after}")
    data_after = wi.models_footprint()
    if data_before is not None and data_after != data_before:
        raise AssertionError(f"modelli dell'utente toccati: prima {data_before}, dopo {data_after}")
    lines.append(f"cartella e registro puliti; modelli dell'utente intatti {data_after}")
    return lines


def _selftest(exe: Path, report: Path) -> bool:
    command = [sys.executable, str(HERE / "run_selftest.py"), str(exe), str(report)]
    return subprocess.run(command).returncode == 0


def _run_case(setup: Path, case: Case, report: Path, args: argparse.Namespace) -> dict:
    name, target, desktop = case
    print(f"\n=== {name}: {target or 'cartella predefinita'}", flush=True)
    associations = wi.default_associations()
    data_before = wi.models_footprint()
    result: dict = {"case": name, "requested_dir": str(target) if target else None,
                    "desktop_icon": desktop, "ok": False}
    log = report.with_name(f"{report.stem}.{name}.install.log")
    app_dir = _install(setup, target, log, desktop)
    try:
        result.update(installed_dir=str(app_dir), installed_dir_chars=len(str(app_dir)),
                      installed_bytes=wi.tree_size(app_dir), longest_path_chars=wi.longest_path(app_dir))
        result["checks"] = _check_installed(app_dir, associations, desktop)
        if not args.skip_selftest:
            result["selftest_report"] = str(report.with_name(f"{report.stem}.{name}.selftest.json"))
            result["selftest_ok"] = _selftest(app_dir / wi.APP_EXE, Path(result["selftest_report"]))
        if not args.skip_open_with:
            result["checks"].append(wi.check_open_with_launch(app_dir, _OPEN_WITH_ALIVE_S))
    finally:
        _uninstall()
    result["checks"] += _check_removed(app_dir, associations, data_before)
    result["ok"] = result.get("selftest_ok", True)
    for line in result["checks"]:
        print(f"  ok: {line}", flush=True)
    return result


def _long_dir(scratch: Path) -> Path:
    long_dir = scratch
    while len(str(long_dir)) < _LONG_PATH_MIN_CHARS:
        long_dir = long_dir / "percorso molto lungo per il collaudo"
    return long_dir / "StemForge"


def _dir_of_length(base: Path, length: int) -> Path:
    """Una cartella sotto `base` lunga esattamente `length` caratteri."""
    padding = length - len(str(base / "StemForge")) - 1
    if padding < 1:
        raise AssertionError(f"{base} è già più lunga di {length} caratteri")
    return base / ("p" * padding) / "StemForge"


def _probe_long_dir(setup: Path, target: Path, report: Path) -> dict:
    """Inno Setup non scrive oltre MAX_PATH nemmeno con i percorsi lunghi di
    Windows attivi: se l'app non ci sta, l'installer deve rifiutare la
    cartella PRIMA di copiare, con un errore e senza lasciare niente."""
    print(f"\n=== lungo-oltre-il-limite: {target} ({len(str(target))} caratteri)", flush=True)
    log = report.with_name(f"{report.stem}.lungo-oltre-il-limite.install.log")
    code = _run_setup(setup, target, log)
    result = {"case": "lungo-oltre-il-limite", "requested_dir": str(target),
              "requested_dir_chars": len(str(target)), "exit_code": code, "ok": True}
    if code == 0 and wi.installed_dir() is not None:
        _uninstall()  # l'app ci sta: il caso "lungo" la collauda per intero lì
        return {**result, "accepted": True, "max_dir_chars": None}
    limit = wi.refused_max_dir(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
    if limit is None or wi.installed_dir() is not None or target.exists():
        raise AssertionError(f"cartella lunga né installata né rifiutata pulita (uscita {code}, log {log})")
    print(f"  ok: rifiutata prima di copiare (uscita {code}), massimo accettato {limit} caratteri", flush=True)
    return {**result, "accepted": False, "max_dir_chars": limit}


def _cases(args: argparse.Namespace, scratch: Path) -> list[Case]:
    if args.dir:
        return [("dir", Path(args.dir), False)]
    if not args.matrix:
        return [("temporanea", scratch / "StemForge", False)]
    accented = scratch / "Cartella con spazi àèéìòù ÄÖÜ ñ" / "StemForge"
    # l'icona sul desktop (opzionale) si prova una volta: va sul Desktop vero, anche se è in OneDrive
    return [("predefinita", None, False), ("spazi-accenti", accented, True)]


def _long_cases(setup: Path, scratch: Path, report: Path, args: argparse.Namespace) -> list[dict]:
    """Oltre 200 caratteri se l'app ci sta, altrimenti il rifiuto pulito e
    poi il collaudo completo nella cartella più lunga che l'installer accetta."""
    probe = _probe_long_dir(setup, _long_dir(scratch), report)
    target = _long_dir(scratch) if probe["accepted"] else _dir_of_length(scratch, probe["max_dir_chars"])
    return [probe, _run_case(setup, ("lungo", target, False), report, args)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("setup", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--dir")
    parser.add_argument("--skip-selftest", action="store_true")
    parser.add_argument("--skip-open-with", action="store_true")
    args = parser.parse_args()
    setup, report = args.setup.resolve(), args.report.resolve()
    if wi.installed_dir() is not None:
        print(f"StemForge è già installato in {wi.installed_dir()}: non lo tocco", file=sys.stderr)
        return 2
    report.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="stemforge-install-"))
    container = wi.virtualized_localappdata()
    if container:
        print(f"ATTENZIONE: %LOCALAPPDATA% è deviata in {container} (contenitore MSIX): anche "
              "%APPDATA% e HKCU lo sono, Esplora risorse dell'utente non vedrà l'installazione",
              flush=True)
    summary = {"installer": str(setup), "installer_bytes": setup.stat().st_size,
               "msix_virtualized_localappdata": str(container) if container else None, "cases": []}
    for case in _cases(args, scratch):
        summary["cases"].append(_run_case(setup, case, report, args))
    if args.matrix and not args.dir:
        summary["cases"] += _long_cases(setup, scratch, report, args)
    summary["ok"] = all(case["ok"] for case in summary["cases"])
    shutil.rmtree(scratch)  # dopo le disinstallazioni verificate restano solo cartelle vuote
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nINSTALLER COLLAUDATO" if summary["ok"] else "\nINSTALLER: COLLAUDO FALLITO", flush=True)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
