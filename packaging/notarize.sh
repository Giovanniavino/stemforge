#!/bin/sh
# Firma Developer ID + notarizzazione Apple (BUILD_SPEC §9.3).
#
# La CI la chiama da sola SE nei secrets del repository ci sono le
# credenziali Apple (README, "Distribuzione firmata"); altrimenti l'app
# resta firmata ad-hoc da PyInstaller e l'utente la apre come spiega la
# documentazione.
#
#   APPLE_SIGNING_IDENTITY="Developer ID Application: Nome (TEAMID)" \
#   APPLE_ID=... APPLE_TEAM_ID=... APPLE_APP_PASSWORD=... \
#   sh packaging/notarize.sh packaging/dist/StemForge.app dist/StemForge-1.0.0-macos-arm64.dmg
#
# Ordine obbligato: si firma dall'interno verso l'esterno (ogni Mach-O,
# poi i framework, poi gli eseguibili principali, poi il bundle) con
# hardened runtime e timestamp. Niente --deep in firma: deprecato e
# incoerente sui bundle PyInstaller (in verifica invece serve).
# Strumenti: codesign, hdiutil, xcrun notarytool/stapler, spctl di
# macOS 14-15 (Xcode 15+; altool non esiste piu').
set -eu

APP="${1:?uso: notarize.sh StemForge.app output.dmg}"
DMG="${2:?uso: notarize.sh StemForge.app output.dmg}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
ENTITLEMENTS="$HERE/entitlements.plist"
PYTHON="${PYTHON:-python3}"

# Tutte le credenziali PRIMA di firmare: scoprire che manca la password
# dopo dieci minuti di codesign non serve a nessuno.
IDENTITY="${APPLE_SIGNING_IDENTITY:?serve APPLE_SIGNING_IDENTITY}"
: "${APPLE_ID:?serve APPLE_ID}" "${APPLE_TEAM_ID:?serve APPLE_TEAM_ID}"
: "${APPLE_APP_PASSWORD:?serve APPLE_APP_PASSWORD}"
[ -d "$APP/Contents/MacOS" ] || { echo "non e' un .app: $APP" >&2; exit 1; }

# Gate licenze (§5.8 punto 3): una build con pesi non verificati non esce.
"$PYTHON" "$HERE/macos/license_gate.py" --root "$REPO"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

sign() {  # $1 = percorso, $2 = "entitlements" per gli eseguibili dell'app
    if [ "${2:-}" = "entitlements" ]; then
        codesign --force --timestamp --options runtime \
            --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$1"
    else
        codesign --force --timestamp --options runtime --sign "$IDENTITY" "$1"
    fi
}

deepest_first() {  # righe di percorsi -> dalla piu' profonda alla meno profonda
    awk -F/ '{ print NF "\t" $0 }' | sort -t "$(printf '\t')" -k1,1nr | cut -f2-
}

# Ogni Mach-O, non solo *.dylib e *.so: libpython ("Python"), il FFmpeg
# in Frameworks/ffmpeg/ e gli eseguibili di torch non hanno estensione,
# e un solo binario senza firma Developer ID fa respingere la notarizzazione.
find "$APP/Contents" -type f ! -path "$APP/Contents/MacOS/*" | while IFS= read -r file; do
    case "$(file -b "$file")" in Mach-O*) printf '%s\n' "$file" ;; esac
done | deepest_first > "$WORK/macho.txt"
find "$APP/Contents" -type d -name "*.framework" | deepest_first > "$WORK/frameworks.txt"

echo "firmo $(wc -l < "$WORK/macho.txt" | tr -d ' ') binari interni..."
while IFS= read -r file; do sign "$file"; done < "$WORK/macho.txt"
echo "firmo $(wc -l < "$WORK/frameworks.txt" | tr -d ' ') framework..."
while IFS= read -r framework; do sign "$framework"; done < "$WORK/frameworks.txt"
echo "firmo gli eseguibili dell'app (con entitlements: torch, §9.3)..."
find "$APP/Contents/MacOS" -type f -perm -u+x > "$WORK/main.txt"
while IFS= read -r binary; do sign "$binary" entitlements; done < "$WORK/main.txt"
sign "$APP" entitlements
codesign --verify --deep --strict --verbose=2 "$APP"

echo "impacchetto e notarizzo..."
sh "$HERE/macos/make_dmg.sh" "$APP" "$DMG"
codesign --force --timestamp --sign "$IDENTITY" "$DMG"
# notarytool puo' uscire con 0 anche se Apple respinge: conta lo "status"
xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" --wait --output-format json > "$WORK/submit.json"
STATUS="$("$PYTHON" -c 'import json, sys; print(json.load(open(sys.argv[1])).get("status", ""))' "$WORK/submit.json")"
if [ "$STATUS" != "Accepted" ]; then
    echo "notarizzazione NON accettata (status: ${STATUS:-sconosciuto})" >&2
    cat "$WORK/submit.json" >&2
    SUBMISSION="$("$PYTHON" -c 'import json, sys; print(json.load(open(sys.argv[1])).get("id", ""))' "$WORK/submit.json")"
    if [ -n "$SUBMISSION" ]; then
        xcrun notarytool log "$SUBMISSION" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
            --password "$APPLE_APP_PASSWORD" >&2 || true
    fi
    exit 1
fi
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG"
spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
echo "notarizzazione completata: $DMG"
