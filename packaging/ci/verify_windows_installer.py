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
percorso oltre 200 caratteri (§9.7); senza, solo una cartella temporanea
(o quella di --dir). Il riepilogo va in <report.json>, i --selftest
accanto, uno per caso.
"""

from __future__ import annotations

import argparse
import json
import os
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


def _install(setup: Path, target: Path | None, log: Path) -> Path:
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", f"/LOG={log}"]
    if target is not None:
        command.append(f"/DIR={target}")
    code = subprocess.run(command, timeout=_INSTALL_TIMEOUT_S).returncode
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


def _check_installed(app_dir: Path, associations: dict[str, dict[str, str | None]]) -> list[str]:
    exe = app_dir / wi.APP_EXE
    lines = [wi.check_start_menu(exe), wi.check_no_desktop_icon(), wi.check_open_with(exe)]
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


def _run_case(setup: Path, name: str, target: Path | None, report: Path, args: argparse.Namespace) -> dict:
    print(f"\n=== {name}: {target or 'cartella predefinita'}", flush=True)
    associations = wi.default_associations()
    data_before = wi.models_footprint()
    result: dict = {"case": name, "requested_dir": str(target) if target else None, "ok": False}
    log = report.with_name(f"{report.stem}.{name}.install.log")
    app_dir = _install(setup, target, log)
    try:
        result.update(installed_dir=str(app_dir), installed_dir_chars=len(str(app_dir)),
                      installed_bytes=wi.tree_size(app_dir), longest_path_chars=wi.longest_path(app_dir))
        result["checks"] = _check_installed(app_dir, associations)
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


def _cases(args: argparse.Namespace, scratch: Path) -> list[tuple[str, Path | None]]:
    if args.dir:
        return [("dir", Path(args.dir))]
    if not args.matrix:
        return [("temporanea", scratch / "StemForge")]
    accented = scratch / "Cartella con spazi àèéìòù ÄÖÜ ñ" / "StemForge"
    long_dir = scratch
    while len(str(long_dir)) < _LONG_PATH_MIN_CHARS:
        long_dir = long_dir / "percorso molto lungo per il collaudo"
    return [("predefinita", None), ("spazi-accenti", accented), ("lungo", long_dir / "StemForge")]


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
    summary = {"installer": str(setup), "installer_bytes": setup.stat().st_size, "cases": []}
    for name, target in _cases(args, scratch):
        summary["cases"].append(_run_case(setup, name, target, report, args))
    summary["ok"] = all(case["ok"] for case in summary["cases"])
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nINSTALLER COLLAUDATO" if summary["ok"] else "\nINSTALLER: COLLAUDO FALLITO", flush=True)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
