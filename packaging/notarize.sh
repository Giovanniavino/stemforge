#!/bin/sh
# Notarizzazione per la distribuzione a terzi (BUILD_SPEC §9.3).
# NON è invocato dalla build di default. Richiede un Apple Developer ID.
#
# Uso:
#   STEMFORGE_CODESIGN_IDENTITY="Developer ID Application: ..." \
#   NOTARY_PROFILE="stemforge-notary" ./packaging/notarize.sh dist/StemForge.app
set -eu

APP="${1:?uso: notarize.sh path/StemForge.app}"

# ---------------------------------------------------------------------------
# GATE LICENZE (§5.8 punto 3, §9.3): una build distribuita non può
# referenziare pesi con licenza non-commercial o non chiara. I pesi del
# 2° stadio e RoFormer si adottano a M4/M6: finché uno di questi ha
# WEIGHTS_SHA256 valorizzato, la sua licenza DEVE essere in questa lista.
# ---------------------------------------------------------------------------
CLEARED_LICENSES_FILE="$(dirname "$0")/cleared_licenses.txt"
python3 - <<'PY'
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent if "__file__" in dir() else Path.cwd()
cleared_path = Path("packaging/cleared_licenses.txt")
cleared = set()
if cleared_path.exists():
    cleared = {l.strip() for l in cleared_path.read_text().splitlines() if l.strip()}

blocked = []
for module in ("drumsplit", "vocalsplit", "dereverb", "roformer"):
    path = Path("src/stemforge/engine") / f"{module}.py"
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    match = re.search(r'WEIGHTS_SHA256(?::[^=]+)?=\s*"([0-9a-f]{64})"', text)
    if match and f"{module}:{match.group(1)}" not in cleared:
        blocked.append(module)

if blocked:
    print("GATE LICENZE: pesi adottati senza licenza verificata:", ", ".join(blocked))
    print("Aggiungi 'modulo:sha256' a packaging/cleared_licenses.txt SOLO dopo")
    print("aver verificato per iscritto la licenza (BUILD_SPEC §5.8).")
    sys.exit(1)
print("gate licenze: ok")
PY

xcrun notarytool submit "$APP" --keychain-profile "${NOTARY_PROFILE:?serve NOTARY_PROFILE}" --wait
xcrun stapler staple "$APP"
echo "notarizzazione completata: $APP"
