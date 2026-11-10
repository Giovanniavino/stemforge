#!/bin/sh
# Firma Developer ID + notarizzazione Apple (BUILD_SPEC §9.3).
#
# La CI la chiama da sola SE nei secrets del repository ci sono le
# credenziali Apple (vedi README, "Distribuzione firmata"); altrimenti
# l'app resta firmata ad-hoc e l'utente la apre con click destro -> Apri.
#
#   APPLE_SIGNING_IDENTITY="Developer ID Application: Nome (TEAMID)" \
#   APPLE_ID=... APPLE_TEAM_ID=... APPLE_APP_PASSWORD=... \
#   sh packaging/notarize.sh packaging/dist/StemForge.app dist/StemForge.dmg
#
# Ordine obbligato: si firma dall'interno verso l'esterno (librerie, poi
# eseguibili, poi il bundle) con hardened runtime e timestamp; --deep è
# deprecato e su un bundle PyInstaller produce firme incoerenti.
set -eu

APP="${1:?uso: notarize.sh StemForge.app output.dmg}"
DMG="${2:?uso: notarize.sh StemForge.app output.dmg}"
IDENTITY="${APPLE_SIGNING_IDENTITY:?serve APPLE_SIGNING_IDENTITY}"
ENTITLEMENTS="$(cd "$(dirname "$0")" && pwd)/entitlements.plist"

# ---------------------------------------------------------------------------
# GATE LICENZE (§5.8 punto 3): una build distribuita non può contenere pesi
# con licenza non-commercial o non verificata. Ogni modello di 2° stadio
# adottato (WEIGHTS_SHA256 valorizzato) deve stare in cleared_licenses.txt.
# ---------------------------------------------------------------------------
python3 - <<'PY'
import re
import sys
from pathlib import Path

cleared_path = Path("packaging/cleared_licenses.txt")
cleared = set()
if cleared_path.exists():
    cleared = {l.strip() for l in cleared_path.read_text().splitlines() if l.strip()}
blocked = []
for module in ("drumsplit", "vocalsplit", "dereverb", "roformer"):
    path = Path("src/stemforge/engine") / f"{module}.py"
    if not path.exists():
        continue
    match = re.search(r'WEIGHTS_SHA256(?::[^=]+)?=\s*"([0-9a-f]{64})"', path.read_text(encoding="utf-8"))
    if match and f"{module}:{match.group(1)}" not in cleared:
        blocked.append(module)
if blocked:
    print("GATE LICENZE: pesi adottati senza licenza verificata:", ", ".join(blocked))
    print("Aggiungi 'modulo:sha256' a packaging/cleared_licenses.txt SOLO dopo")
    print("aver verificato per iscritto la licenza (BUILD_SPEC §5.8).")
    sys.exit(1)
print("gate licenze: ok")
PY

sign() {
    codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" \
        --sign "$IDENTITY" "$1"
}

echo "firmo le librerie..."
find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) | while read -r lib; do
    sign "$lib"
done
echo "firmo i framework..."
find "$APP/Contents" -type d -name "*.framework" -prune | while read -r framework; do
    sign "$framework"
done
echo "firmo gli eseguibili..."
find "$APP/Contents/MacOS" -type f -perm -u+x | while read -r binary; do
    sign "$binary"
done
sign "$APP"
codesign --verify --strict --verbose=2 "$APP"

echo "impacchetto e notarizzo..."
sh "$(dirname "$0")/macos/make_dmg.sh" "$APP" "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"
xcrun notarytool submit "$DMG" \
    --apple-id "${APPLE_ID:?serve APPLE_ID}" \
    --team-id "${APPLE_TEAM_ID:?serve APPLE_TEAM_ID}" \
    --password "${APPLE_APP_PASSWORD:?serve APPLE_APP_PASSWORD}" \
    --wait
xcrun stapler staple "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
echo "notarizzazione completata: $DMG"
