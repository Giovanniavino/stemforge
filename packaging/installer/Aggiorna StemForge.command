#!/bin/sh
# ============================================================================
# Aggiornamento rapido di StemForge (doppio click).
#
# Riusa l'ambiente creato dall'installazione completa: NON riscarica
# Python ne' le dipendenze (~1 GB), ricostruisce solo l'app con i
# sorgenti aggiornati e la sostituisce in /Applications. Pochi minuti.
#
# Se l'installazione completa non e' mai stata fatta su questo Mac,
# questo script si ferma e ti dice di usare "Installa StemForge.command".
# ============================================================================
set -eu

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die() {
    printf '\n\033[31mERRORE: %s\033[0m\n\n' "$1"
    printf 'Premi Invio per chiudere...'
    read -r _
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_ENV="$HOME/Library/Application Support/StemForge/build-env"

# Stessi due layout dell'installer: pacchetto distribuito o repo.
if [ -f "$SCRIPT_DIR/StemForge/requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$SCRIPT_DIR/StemForge"
elif [ -f "$SCRIPT_DIR/../../requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
    die "sorgenti di StemForge non trovati accanto a questo script.
Estrai TUTTO lo zip e rilancia."
fi

if [ "$(uname -m)" = "arm64" ]; then
    if arch -x86_64 /usr/bin/true 2>/dev/null; then
        exec arch -x86_64 /bin/sh "$0" "$@"
    else
        die "serve Rosetta 2: esegui prima 'softwareupdate --install-rosetta'."
    fi
fi

say "Controllo l'ambiente esistente"
PYBIN="$BUILD_ENV/bin/python"
[ -x "$PYBIN" ] || die "ambiente di costruzione non trovato: su questo Mac
serve prima l'installazione completa (Installa StemForge.command)."
"$PYBIN" -c "import torch, PySide6" 2>/dev/null \
    || die "l'ambiente esistente e' incompleto: rifai l'installazione
completa con Installa StemForge.command."
echo "    ambiente ok, niente da riscaricare."

say "Aggiorno i sorgenti di StemForge"
"$PYBIN" -m pip install --quiet "$SRC_DIR" --no-deps --no-build-isolation --force-reinstall \
    || die "aggiornamento dei sorgenti non riuscito: manda le righe qui sopra a chi ti ha dato il pacchetto."

say "Ricostruisco l'app (qualche minuto)"
cd "$SRC_DIR/packaging"
rm -rf build dist
"$BUILD_ENV/bin/pyinstaller" stemforge.spec --noconfirm --log-level ERROR \
    || die "ricostruzione non riuscita: manda le righe qui sopra a chi ti ha dato il pacchetto."
[ -d "dist/StemForge.app" ] || die "l'app non risulta costruita."

say "Sostituisco StemForge in /Applications"
rm -rf "/Applications/StemForge.app"
ditto "dist/StemForge.app" "/Applications/StemForge.app" || die "copia in /Applications non riuscita."
rm -rf build dist

printf '\n\033[32m\033[1mAggiornamento completato.\033[0m\n'
printf 'I modelli gia'\'' scaricati e la calibrazione restano al loro posto.\n\n'
printf 'Premi Invio per aprire StemForge...'
read -r _
open "/Applications/StemForge.app"
