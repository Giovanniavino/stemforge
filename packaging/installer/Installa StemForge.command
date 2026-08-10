#!/bin/sh
# ============================================================================
# Installer di StemForge per Mac Intel (doppio click).
#
# Cosa fa, nell'ordine:
#   1. controlla il Mac (macOS 12+, architettura);
#   2. se manca Python 3.11, scarica quello ufficiale di python.org
#      e lo installa (chiede la password di amministratore);
#   3. installa le dipendenze ESATTE del progetto, con verifica
#      dell'integrita' (hash SHA-256) di ogni pacchetto;
#   4. costruisce StemForge.app NATIVAMENTE su questo Mac (cosi' macOS
#      non la tratta come app di uno sviluppatore sconosciuto);
#   5. la copia in /Applications.
#
# Serve la connessione a internet. Al primo avvio l'app scarichera' i
# modelli di separazione (~1 GB, una volta sola).
# ============================================================================
set -eu

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die() {
    printf '\n\033[31mERRORE: %s\033[0m\n\n' "$1"
    printf 'Premi Invio per chiudere...'
    read -r _
    exit 1
}

cd "$(dirname "$0")"

# 3.11 obbligato: PySide6 6.4 (l'ultima Qt per macOS < 11) richiede < 3.12.
PY_VERSION="3.11.9"
PY_PKG_URL="https://www.python.org/ftp/python/${PY_VERSION}/python-${PY_VERSION}-macos11.pkg"
BUILD_ENV="$HOME/Library/Application Support/StemForge/build-env"
SRC_DIR="$PWD/StemForge"

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
    # Mac Apple Silicon: StemForge e' costruita per Intel; via Rosetta funziona.
    if arch -x86_64 /usr/bin/true 2>/dev/null; then
        say "Mac Apple Silicon: proseguo tramite Rosetta 2"
        exec arch -x86_64 /bin/sh "$0" "$@"
    else
        die "serve Rosetta 2: esegui prima 'softwareupdate --install-rosetta' nel Terminale."
    fi
fi
echo "    macOS $(sw_vers -productVersion), Intel x86_64: ok."

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
PYBIN="$BUILD_ENV/bin/python"
"$PYBIN" -m pip install --quiet --upgrade pip || die "aggiornamento di pip non riuscito."

say "Scarico le dipendenze (ogni pacchetto e' verificato con hash SHA-256)"
"$PYBIN" -m pip install --quiet --require-hashes -r "$SRC_DIR/requirements-macos-x86_64.lock" \
    || die "installazione dipendenze non riuscita. Controlla la connessione e riprova."
"$PYBIN" -m pip install --quiet setuptools wheel "pyinstaller>=6.6,<7" || die "strumenti di build non installabili."
"$PYBIN" -m pip install --quiet "$SRC_DIR" --no-deps --no-build-isolation || die "installazione di StemForge non riuscita."

# ------------------------------------------------------------ 4. build .app
say "Costruisco StemForge.app su questo Mac"
cd "$SRC_DIR/packaging"
rm -rf build dist
"$BUILD_ENV/bin/pyinstaller" stemforge.spec --noconfirm --log-level ERROR \
    || die "costruzione dell'app non riuscita."
[ -d "dist/StemForge.app" ] || die "l'app non risulta costruita."

# ------------------------------------------------------- 5. in /Applications
say "Copio StemForge in /Applications"
rm -rf "/Applications/StemForge.app"
ditto "dist/StemForge.app" "/Applications/StemForge.app" || die "copia in /Applications non riuscita."
rm -rf build dist

printf '\n\033[32m\033[1mFatto! StemForge e'\'' in /Applications.\033[0m\n'
printf 'Al primo avvio scarichera'\'' i modelli (~1 GB, una volta sola)\n'
printf 'e misurera'\'' la velocita'\'' di questo Mac per darti stime oneste.\n\n'
printf 'Premi Invio per aprire StemForge ora (o chiudi questa finestra)...'
read -r _
open "/Applications/StemForge.app"
