#!/bin/sh
# Impacchetta StemForge.app in un DMG "trascina in Applicazioni" (§9.6).
#
#   sh packaging/macos/make_dmg.sh packaging/dist/StemForge.app dist/StemForge-1.0.0-macos-arm64.dmg
#
# Formato UDZO (zlib) su HFS+: leggibile da macOS 10.15 in poi, cioè da
# tutti i Mac che StemForge supporta. HFS+ esplicito: il default di
# hdiutil puo' cambiare fra versioni di macOS, e il runner e' un 14-15.
# Niente strumenti di terze parti: solo hdiutil e ditto.
set -eu

APP="${1:?uso: make_dmg.sh StemForge.app output.dmg}"
OUT="${2:?uso: make_dmg.sh StemForge.app output.dmg}"

[ -d "$APP/Contents/MacOS" ] || { echo "app non trovata: $APP" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
ditto "$APP" "$STAGING/StemForge.app"
ln -s /Applications "$STAGING/Applications"

# hdiutil sui runner di CI fallisce a volte con "Resource busy": si riprova
attempt=1
until hdiutil create -volname "StemForge" -srcfolder "$STAGING" -ov \
        -fs HFS+ -format UDZO -imagekey zlib-level=9 "$OUT"; do
    if [ "$attempt" -ge 5 ]; then
        echo "hdiutil non riesce a creare il DMG" >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 5
done

hdiutil verify "$OUT"
echo "DMG creato: $OUT"
