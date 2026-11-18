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
REQUIRED_MODULES="ssl, ctypes, lzma, bz2, zlib, sqlite3, uuid"

die() { echo "build_python.sh: ERRORE: $*" >&2; exit 1; }
log() { echo "build_python.sh: $*" >&2; }

[ $# -eq 1 ] || die "uso: $0 PREFIX"
PREFIX="$1"
STAMP="$PREFIX/.stemforge-python"
PYTHON="$PREFIX/bin/python3.12"

if [ -x "$PYTHON" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$PY_VERSION $PY_SHA256" ]; then
    log "Python $PY_VERSION gia' in $PREFIX"
    exit 0
fi

install_build_deps() {
    if [ "${STEMFORGE_SKIP_SYSTEM_PACKAGES:-0}" = "1" ]; then
        return
    fi
    log "librerie di sviluppo per i moduli della libreria standard"
    dnf -y -q install openssl-devel libffi-devel bzip2-devel xz-devel \
        sqlite-devel libuuid-devel zlib-devel make
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
        # $$ORIGIN: il Makefile lo passa al linker come $ORIGIN, cosi'
        # python3.12 trova la propria libpython senza LD_LIBRARY_PATH.
        # Niente --enable-optimizations: il tempo dell'app e' in torch, non
        # nell'interprete, e la PGO triplica la durata della build.
        # shellcheck disable=SC2016 # $$ORIGIN e' per make e ld, non per bash
        ./configure --prefix="$PREFIX" --enable-shared --with-ensurepip=no \
            LDFLAGS='-Wl,-rpath,$$ORIGIN/../lib' >/dev/null
        make -j"$(nproc)" >/dev/null
        rm -rf "$PREFIX"
        make install >/dev/null
    )
}

check_result() {
    "$PYTHON" - "$REQUIRED_MODULES" <<'PY' || die "Python costruito senza un modulo richiesto"
import importlib
import sys
import sysconfig

if not sysconfig.get_config_var("Py_ENABLE_SHARED"):
    sys.exit("libpython non condivisa: PyInstaller non potrebbe usarla")
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
    echo "$PY_VERSION $PY_SHA256" > "$STAMP"
    log "Python $PY_VERSION pronto: $PYTHON"
}

main "$@"
