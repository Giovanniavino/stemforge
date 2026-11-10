#!/bin/sh
# ============================================================================
# Installer di StemForge per Mac Intel (doppio click). BUILD_SPEC §9.5.
#
# Cosa fa, nell'ordine:
#   1. controlla il Mac (macOS 10.15+, Intel; Apple Silicon via Rosetta);
#   2. se manca Python 3.11, scarica quello ufficiale di python.org
#      e lo installa (chiede la password di amministratore);
#   3. installa le dipendenze ESATTE del progetto, con verifica
#      dell'integrita' (hash SHA-256) di ogni pacchetto;
#   4. costruisce StemForge.app NATIVAMENTE su questo Mac (cosi' macOS
#      non la tratta come app di uno sviluppatore sconosciuto), con il
#      decoder FFmpeg LGPL se lo zip lo contiene;
#   5. la copia in /Applications.
#
# Serve la connessione a internet. Al primo avvio l'app scarichera' i
# modelli di separazione (~1 GB, una volta sola).
# ============================================================================
set -eu

die() {
    printf '\n\033[31mERRORE: %s\033[0m\n\n' "$1"
    printf 'Premi Invio per chiudere...'
    read -r _
    exit 1
}

# Percorso assoluto dello script PRIMA di qualsiasi cd: regge sia il
# doppio click sia l'invocazione manuale con percorso relativo.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_PATH="$SCRIPT_DIR/$(basename "$0")"
cd "$SCRIPT_DIR"

# Due layout possibili: il pacchetto distribuito (StemForge/ accanto a
# questo script) o il repo (script in packaging/installer/, sorgenti due
# livelli sopra). Errore chiaro se non e' nessuno dei due.
if [ -f "$SCRIPT_DIR/StemForge/requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$SCRIPT_DIR/StemForge"
elif [ -f "$SCRIPT_DIR/../../requirements-macos-x86_64.lock" ]; then
    SRC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
    die "sorgenti di StemForge non trovati accanto all'installer.
Estrai TUTTO lo zip (non solo questo file) e rilancia lo script
dalla cartella estratta."
fi
[ -f "$SRC_DIR/packaging/installer/comune.sh" ] \
    || die "pacchetto incompleto (manca comune.sh): riscarica lo zip ed estrailo TUTTO."
# shellcheck source=comune.sh
. "$SRC_DIR/packaging/installer/comune.sh"

# 3.11 obbligato: PySide6 6.4 (l'ultima Qt per macOS < 11) richiede < 3.12.
# Il pacchetto "macos11" di python.org e' universal2 e gira da macOS 10.9.
PY_VERSION="3.11.9"
PY_PKG_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-macos11.pkg"

# ---------------------------------------------------------------- 1. il Mac
say "Controllo questo Mac"
[ "$(uname -s)" = "Darwin" ] || die "questo installer e' solo per macOS."
MACOS_VERSION=$(sw_vers -productVersion)
MACOS_MAJOR=$(printf '%s' "$MACOS_VERSION" | cut -d. -f1)
MACOS_MINOR=$(printf '%s' "$MACOS_VERSION" | cut -d. -f2)
if [ "$MACOS_MAJOR" -lt 10 ] || { [ "$MACOS_MAJOR" -eq 10 ] && [ "${MACOS_MINOR:-0}" -lt 15 ]; }; then
    die "serve macOS 10.15 Catalina o successivo (questo e' $MACOS_VERSION)."
fi

if [ "$(uname -m)" = "arm64" ]; then
    # Mac Apple Silicon: questa build e' per Intel e via Rosetta funziona,
    # ma piu' lenta e senza GPU: il DMG arm64 e' la scelta giusta (§9.1).
    if arch -x86_64 /usr/bin/true 2>/dev/null; then
        say "Mac Apple Silicon: proseguo tramite Rosetta 2 (il DMG arm64 sarebbe piu' veloce)"
        exec arch -x86_64 /bin/sh "$SCRIPT_PATH" "$@"
    else
        die "serve Rosetta 2: esegui prima 'softwareupdate --install-rosetta' nel Terminale."
    fi
fi
echo "    macOS $MACOS_VERSION, Intel x86_64: ok."

# ------------------------------------------------------------- 2. Python
say "Cerco Python 3.11"
PYTHON=""
for candidate in \
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11" \
    "/usr/local/bin/python3.11" \
    "$(command -v python3.11 2>/dev/null || true)"
do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    say "Python 3.11 non trovato: scarico quello ufficiale (python.org)"
    PKG="/tmp/stemforge-python-${PY_VERSION}.pkg"
    curl -fL --progress-bar "$PY_PKG_URL" -o "$PKG" || die "download di Python non riuscito. Controlla la connessione e riprova."
    say "Installo Python ${PY_VERSION} (ti chiedera' la password)"
    sudo installer -pkg "$PKG" -target / || die "installazione di Python non riuscita."
    rm -f "$PKG"
    PYTHON="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
    [ -x "$PYTHON" ] || die "Python installato ma non trovato dove atteso."
fi
echo "    uso: $PYTHON ($("$PYTHON" -c 'import platform; print(platform.python_version())'))"

# -------------------------------------------------- 3. dipendenze verificate
say "Preparo l'ambiente di costruzione (puo' richiedere qualche minuto)"
rm -rf "$BUILD_ENV"
"$PYTHON" -m venv "$BUILD_ENV" || die "creazione dell'ambiente non riuscita."
"$PYBIN" -m pip install --quiet --upgrade pip || die "aggiornamento di pip non riuscito."

say "Scarico le dipendenze (~1 GB: possono volerci DECINE DI MINUTI, il progresso e' visibile qui sotto)"
install_locked_deps

# ------------------------------------------------------------ 4. build .app
say "Costruisco StemForge.app su questo Mac"
prepare_ffmpeg
build_app

# ------------------------------------------------------- 5. in /Applications
say "Copio StemForge in /Applications"
copy_to_applications

printf '\n\033[32m\033[1mFatto! StemForge e'\'' in /Applications.\033[0m\n'
ffmpeg_notice
printf '\nAl primo avvio scarichera'\'' i modelli (~1 GB, una volta sola)\n'
printf 'e misurera'\'' la velocita'\'' di questo Mac per darti stime oneste.\n\n'
printf 'Premi Invio per aprire StemForge ora (o chiudi questa finestra)...'
read -r _
open "$APP_DEST"
