#!/bin/sh
# ============================================================================
# Aggiornamento di StemForge (doppio click). BUILD_SPEC §9.5.
#
# Riusa l'ambiente creato dall'installazione completa: NON riscarica
# Python. Porta l'ambiente al lock di questa versione (pip scarica solo
# i pacchetti nuovi o cambiati, ognuno verificato con l'hash SHA-256),
# ricostruisce l'app con i sorgenti aggiornati e la sostituisce in
# /Applications. Di solito pochi minuti.
#
# Se l'installazione completa non e' mai stata fatta su questo Mac,
# questo script si ferma e ti dice di usare "Installa StemForge.command".
# ============================================================================
set -eu

die() {
    printf '\n\033[31mERRORE: %s\033[0m\n\n' "$1"
    printf 'Premi Invio per chiudere...'
    read -r _
    exit 1
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "$0")"
cd "$SCRIPT_DIR"

# Stessi due layout dell'installer: pacchetto distribuito o repo.
if [ -f "$SCRIPT_DIR/StemForge/requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$SCRIPT_DIR/StemForge"
elif [ -f "$SCRIPT_DIR/../../requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
    die "sorgenti di StemForge non trovati accanto a questo script.
Estrai TUTTO lo zip e rilancia."
fi
[ -f "$SRC_DIR/packaging/installer/comune.sh" ] \
    || die "pacchetto incompleto (manca comune.sh): riscarica lo zip ed estrailo TUTTO."
# shellcheck source=comune.sh
. "$SRC_DIR/packaging/installer/comune.sh"

if [ "$(uname -m)" = "arm64" ]; then
    if arch -x86_64 /usr/bin/true 2>/dev/null; then
        exec arch -x86_64 /bin/sh "$SCRIPT_PATH" "$@"
    else
        die "serve Rosetta 2: esegui prima 'softwareupdate --install-rosetta'."
    fi
fi

say "Controllo l'ambiente esistente"
[ -x "$PYBIN" ] || die "ambiente di costruzione non trovato: su questo Mac
serve prima l'installazione completa (Installa StemForge.command)."
# un ambiente di prima del passaggio a Catalina puo' avere un altro Python
is_python311_intel "$PYBIN" \
    || die "l'ambiente esistente non usa Python 3.11 per Intel: rifai l'installazione
completa con Installa StemForge.command."

say "Allineo le dipendenze a questa versione (scarico solo cio' che manca)"
install_locked_deps
"$PYBIN" -c "import torch, PySide6" \
    || die "l'ambiente e' incompleto anche dopo l'allineamento: rifai
l'installazione completa con Installa StemForge.command."
echo "    ambiente ok."

say "Ricostruisco l'app (qualche minuto)"
prepare_ffmpeg
build_app

say "Sostituisco StemForge in /Applications"
copy_to_applications

printf '\n\033[32m\033[1mAggiornamento completato.\033[0m\n'
ffmpeg_notice
printf '\nI modelli gia'\'' scaricati e la calibrazione restano al loro posto.\n\n'
printf 'Premi Invio per aprire StemForge...'
read -r _
open "$APP_DEST"
