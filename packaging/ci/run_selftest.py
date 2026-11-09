"""Lancia il collaudo di un'app impacchettata e ne riporta l'esito in CI.

    python packaging/ci/run_selftest.py <eseguibile> <report.json> [--offline]

Passa da subprocess e non dalla shell: su Windows StemForge.exe è
un'applicazione a finestra, e PowerShell non aspetterebbe la sua fine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_TIMEOUT_S = 60 * 60


def main() -> int:
    exe, report = sys.argv[1], Path(sys.argv[2])
    command = [exe, "--selftest", "--report", str(report), *sys.argv[3:]]
    print("$", " ".join(command), flush=True)
    proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=_TIMEOUT_S)
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if not report.exists():
        print(f"nessun report prodotto (uscita {proc.returncode})", file=sys.stderr)
        return proc.returncode or 1
    data = json.loads(report.read_text(encoding="utf-8"))
    for check in data["checks"]:
        print(f"[{check['status']:>4}] {check['name']}")
        if check["status"] == "fail":
            print(check["detail"])
    ok = bool(data["ok"]) and proc.returncode == 0
    print("COLLAUDO RIUSCITO" if ok else "COLLAUDO FALLITO")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
