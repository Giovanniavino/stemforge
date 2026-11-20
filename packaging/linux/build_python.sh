#!/usr/bin/env bash
# CPython 3.12 con libpython condivisa, per PyInstaller (BUILD_SPEC §2.2, §9.8).
#
#   packaging/linux/build_python.sh PREFIX
#
# Perche' non /opt/python/cp312-cp312 dell'immagine manylinux: quei Python
# sono compilati --disable-shared (servono a costruire wheel, non app) e
# PyInstaller si ferma con "Python was built without a shared library"
# (visto nel primo giro di build, 10-11-2026). Qui lo stesso sorgente
# ufficiale di python.org, a versione e SHA-256 fissati, con
# --enable-shared, compilato DENTRO manylinux_2_28: la libpython che
# finisce nell'AppImage chiede glibc 2.28, come il resto del pacchetto.
# Compila la macchina di build; quella dell'utente non compila nulla.
#
# Se PREFIX contiene gia' questa versione (file .stemforge-python) non
# rifa' nulla: la CI puo' metterlo in cache con la versione come chiave.
set -euo pipefail

PY_VERSION="3.12.16"
PY_URL="https://www.python.org/ftp/python/$PY_VERSION/Python-$PY_VERSION.tar.xz"
# Uguale al digest firmato nel bundle sigstore di python.org
# (Python-3.12.16.tar.xz.sigstore, identita' thomas@python.org), 18-11-2026.
PY_SHA256="b5796915dc45ff745cfb4e990a7e7c93d6f546328a102ce31448d69ebc37575c"
# I moduli che senza la loro -devel configure salta in silenzio: ssl per
# scaricare i pesi, ctypes per soundfile, lzma/bz2/zlib per i tar e i pesi.
# Niente _uuid (libuuid-devel): uuid ha il ripiego in Python puro, e la
# -devel trascina un aggiornamento di util-linux che nel container senza
# root vero (rootless_container.py) non si installa (file del gruppo tty).
REQUIRED_MODULES="ssl, ctypes, lzma, bz2, zlib, sqlite3"
# Niente readline: il modulo linka libreadline (GPLv3+), che PyInstaller
# porterebbe nel pacchetto MIT (build del 20-11-2026), e a un'app grafica
# non serve. Cambiare queste opzioni cambia lo stamp: la cache si rifa'.
CONFIGURE_OPTIONS="--enable-shared --with-ensurepip=no --without-readline"
# \$$ORIGIN: make toglie un $, il backslash protegge l'altro dalla shell
# della ricetta di link. Con il solo $$ORIGIN la shell espandeva $ORIGIN a
# vuoto e l'rpath diventava "/../lib" (build del 20-11-2026): python3.12
# caricava la libpython 3.12.15 di AlmaLinux al posto della nostra.
# shellcheck disable=SC2016
RPATH_LDFLAGS='-Wl,-rpath,\$$ORIGIN/../lib'

die() { echo "build_python.sh: ERRORE: $*" >&2; exit 1; }
log() { echo "build_python.sh: $*" >&2; }

[ $# -eq 1 ] || die "uso: $0 PREFIX"
PREFIX="$1"
STAMP="$PREFIX/.stemforge-python"
PYTHON="$PREFIX/bin/python3.12"

BUILD_ID="$PY_VERSION $PY_SHA256 $CONFIGURE_OPTIONS $RPATH_LDFLAGS"

if [ -x "$PYTHON" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$BUILD_ID" ]; then
    log "Python $PY_VERSION gia' in $PREFIX"
    exit 0
fi

install_build_deps() {
    if [ "${STEMFORGE_SKIP_SYSTEM_PACKAGES:-0}" = "1" ]; then
        return
    fi
    log "librerie di sviluppo per i moduli della libreria standard"
    dnf -y -q install openssl-devel libffi-devel bzip2-devel xz-devel \
        sqlite-devel zlib-devel make
}

fetch_source() {
    local target="$1"
    if [ ! -f "$target" ] || ! echo "$PY_SHA256  $target" | sha256sum -c --quiet - 2>/dev/null; then
        log "scarico $PY_URL"
        curl -fsSL --retry 3 -o "$target.part" "$PY_URL"
        echo "$PY_SHA256  $target.part" | sha256sum -c --quiet - || die "SHA-256 errato per $PY_URL"
        mv "$target.part" "$target"
    fi
}

compile() {
    local source="$1"
    (
        cd "$source"
        # Niente --enable-optimizations: il tempo dell'app e' in torch, non
        # nell'interprete, e la PGO triplica la durata della build.
        # SC2086: CONFIGURE_OPTIONS va diviso in parole
        # shellcheck disable=SC2086
        ./configure --prefix="$PREFIX" $CONFIGURE_OPTIONS \
            LDFLAGS="$RPATH_LDFLAGS" >/dev/null
        make -j"$(nproc)" >/dev/null
        rm -rf "$PREFIX"
        make install >/dev/null
    )
}

check_result() {
    # Senza LD_LIBRARY_PATH: deve bastare l'rpath. La versione la dice la
    # libpython caricata, quindi una libpython di sistema qui si vede.
    env -u LD_LIBRARY_PATH "$PYTHON" - "$REQUIRED_MODULES" "$PY_VERSION" <<'PY' \
        || die "Python costruito male (vedi sopra)"
import importlib
import platform
import sys
import sysconfig

if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
    sys.exit("libpython non condivisa: PyInstaller non potrebbe usarla")
if platform.python_version() != sys.argv[2]:
    sys.exit(f"caricata la libpython {platform.python_version()}, non la {sys.argv[2]}: rpath sbagliato")
for name in (part.strip() for part in sys.argv[1].split(",")):
    importlib.import_module(name)
PY
}

main() {
    install_build_deps
    local tarball
    # globale, non local: la trap gira a fine script, fuori da main
    SCRATCH="$(mktemp -d)"
    trap 'rm -rf "$SCRATCH"' EXIT
    mkdir -p "$(dirname "$PREFIX")"
    tarball="$(dirname "$PREFIX")/Python-$PY_VERSION.tar.xz"
    fetch_source "$tarball"
    tar -xJf "$tarball" -C "$SCRATCH"
    log "compilo Python $PY_VERSION in $PREFIX"
    compile "$SCRATCH/Python-$PY_VERSION"
    check_result
    echo "$BUILD_ID" > "$STAMP"
    log "Python $PY_VERSION pronto: $PYTHON"
}

main "$@"
