"""packaging/notarize.sh eseguito con sh e con strumenti Apple FINTI (§9.3).

codesign, xcrun, hdiutil, spctl, ditto e file sono sostituiti da script
che registrano come vengono chiamati. Cosi' anche da Windows si prova la
logica dello script: credenziali chieste prima di firmare, firma
dall'interno verso l'esterno, entitlements solo sugli eseguibili
dell'app, niente --deep in firma, verdetto letto dallo "status" e non dal
codice di uscita di notarytool. Che codesign e notarytool VERI accettino
il bundle resta nella checklist manuale (docs/manual/macos.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTARIZE = ROOT / "packaging" / "notarize.sh"
SH = shutil.which("sh")
MACHO_MARK = "MACHO-FINTO"
CREDENTIALS = {"APPLE_SIGNING_IDENTITY": "Developer ID Application: Prova (TEAM123456)",
               "APPLE_ID": "prova@example.com", "APPLE_TEAM_ID": "TEAM123456",
               "APPLE_APP_PASSWORD": "segreto-finto"}

pytestmark = pytest.mark.skipif(SH is None, reason="serve una sh POSIX (Git Bash su Windows)")

# Ogni strumento finto scrive una riga "nome argomenti" nel registro.
FAKE_TOOLS = {
    "codesign": 'echo "codesign $*" >> "$FAKE_LOG"',
    "spctl": 'echo "spctl $*" >> "$FAKE_LOG"',
    "ln": 'echo "ln $*" >> "$FAKE_LOG"',
    "ditto": 'echo "ditto $*" >> "$FAKE_LOG"; cp -R "$1" "$2"',
    "hdiutil": ('echo "hdiutil $1" >> "$FAKE_LOG"\n'
                'if [ "$1" = create ]; then for last; do :; done; : > "$last"; fi'),
    "file": f'if grep -q {MACHO_MARK} "$2"; then echo "Mach-O 64-bit executable x86_64"; '
            'else echo data; fi',
    "xcrun": ('echo "xcrun $1 $2" >> "$FAKE_LOG"\n'
              'if [ "$1 $2" = "notarytool submit" ]; then cat "$FAKE_NOTARY_JSON"; '
              'exit "$FAKE_NOTARY_RC"; fi'),
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _fake_app(root: Path) -> Path:
    app = root / "StemForge.app"
    # "#!" in testa: Git Bash considera eseguibile solo cio' che inizia cosi'
    _write(app / "Contents" / "MacOS" / "StemForge", f"#!/bin/sh\n{MACHO_MARK}\n")
    for inner in ("Frameworks/libtorch_cpu.dylib", "Frameworks/ffmpeg/ffmpeg",
                  "Frameworks/PySide6/Qt/lib/QtCore.framework/Versions/A/QtCore"):
        _write(app / "Contents" / inner, MACHO_MARK)
    _write(app / "Contents" / "Resources" / "base_library.zip", "non un binario")
    return app


def run_notarize(tmp_path: Path, status: str = "Accepted", notary_rc: int = 0,
                 notary_output: str | None = None,
                 credentials: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fakebin = tmp_path / "bin"
    for name, body in FAKE_TOOLS.items():
        _write(fakebin / name, f"#!/bin/sh\n{body}\n")
    log = tmp_path / "log.txt"
    log.touch()
    answer = tmp_path / "submit.json"
    answer.write_text(notary_output if notary_output is not None
                      else json.dumps({"id": "sub-42", "status": status}), encoding="utf-8")
    app = _fake_app(tmp_path)
    env = {**{k: v for k, v in os.environ.items() if k not in CREDENTIALS},
           **(CREDENTIALS if credentials is None else credentials),
           "FAKE_LOG": log.as_posix(), "FAKE_NOTARY_JSON": answer.as_posix(),
           "FAKE_NOTARY_RC": str(notary_rc), "FAKEBIN": fakebin.as_posix(),
           "PYTHON": Path(sys.executable).as_posix()}
    # "C:/..." contiene ":" e spezzerebbe PATH: pwd lo riscrive in /c/... su Git Bash
    script = 'PATH="$(cd "$FAKEBIN" && pwd):$PATH"; export PATH; exec sh "$0" "$1" "$2"'
    result = subprocess.run(
        [SH, "-c", script, NOTARIZE.as_posix(), app.as_posix(), (tmp_path / "out" / "S.dmg").as_posix()],
        capture_output=True, text=True, env=env, timeout=120)
    return result, log.read_text(encoding="utf-8").splitlines()


def _signed(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("codesign --force")]


def test_signs_inside_out_then_notarizes_and_staples(tmp_path):
    result, lines = run_notarize(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    signed = _signed(lines)
    targets = [line.rsplit("/", 1)[-1] for line in signed]
    # il binario dentro il framework prima del framework, i Mach-O interni
    # prima dell'eseguibile, l'eseguibile prima del bundle, il DMG per ultimo
    assert targets.index("QtCore") < targets.index("QtCore.framework")
    assert targets.index("QtCore.framework") < targets.index("StemForge")
    assert targets.index("libtorch_cpu.dylib") < targets.index("StemForge")
    assert targets.index("ffmpeg") < targets.index("StemForge")
    assert targets[-2:] == ["StemForge.app", "S.dmg"]
    assert "base_library.zip" not in targets
    assert all("--deep" not in line for line in signed)
    assert all("--options runtime" in line for line in signed[:-1])
    with_entitlements = [t for t, line in zip(targets, signed) if "--entitlements" in line]
    assert with_entitlements == ["StemForge", "StemForge.app"]
    assert "codesign --verify --deep --strict --verbose=2" in "\n".join(lines)
    tail = [line for line in lines if not line.startswith(("codesign", "ditto", "ln"))]
    assert tail == ["hdiutil create", "hdiutil verify", "xcrun notarytool submit",
                    "xcrun stapler staple", "xcrun stapler validate",
                    tail[-1]]
    assert tail[-1].startswith("spctl --assess --type open")


def test_rejected_notarization_fails_and_prints_apple_log(tmp_path):
    result, lines = run_notarize(tmp_path, status="Invalid")
    assert result.returncode == 1
    assert "notarizzazione NON accettata (status: Invalid)" in result.stderr
    assert "xcrun notarytool log" in lines
    assert not any("stapler" in line for line in lines)


def test_notarytool_error_without_json_fails_without_traceback(tmp_path):
    result, lines = run_notarize(tmp_path, notary_rc=69, notary_output="Error: rete assente")
    assert result.returncode == 1
    assert "status: sconosciuto" in result.stderr
    assert "Traceback" not in result.stderr
    assert "xcrun notarytool log" not in lines  # senza id non c'e' log da chiedere


def test_missing_credential_stops_before_signing_anything(tmp_path):
    partial = {k: v for k, v in CREDENTIALS.items() if k != "APPLE_APP_PASSWORD"}
    result, lines = run_notarize(tmp_path, credentials=partial)
    assert result.returncode != 0
    assert "APPLE_APP_PASSWORD" in result.stderr
    assert lines == []
