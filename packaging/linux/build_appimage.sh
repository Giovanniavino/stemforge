#!/usr/bin/env bash
# AppImage x64 di StemForge, profilo linux-x64 (BUILD_SPEC §2.1, §9.1, §9.8).
#
#   packaging/linux/build_appimage.sh
#
# Gira DENTRO quay.io/pypa/manylinux_2_28_x86_64 (glibc 2.28): ogni
# binario che entra nel pacchetto e' compilato per quella glibc o una
# piu' vecchia, quindi l'AppImage parte su Ubuntu 20.04, Debian 11,
# Fedora 29 e successive. Fuori da quel container lo script si rifiuta:
# una build sulla glibc dell'host girerebbe solo su sistemi recenti, e
# lo si scoprirebbe sulla macchina dell'utente.
#   CI:      job con `container: quay.io/pypa/manylinux_2_28_x86_64@sha256:...`
#   dev-box: python3 packaging/linux/rootless_container.py (vedi il suo doc)
#
# Passi: lock -> venv -> PyInstaller (packaging/stemforge.spec) ->
# librerie di sistema (bundle_libs.py) -> AppDir -> appimagetool.
#
# Variabili (tutte facoltative):
#   STEMFORGE_LOCK      lock con hash (default: requirements-linux-x64.lock)
#   STEMFORGE_WORK      cartella di lavoro (default: build/appimage)
#   STEMFORGE_DIST      dove scrivere l'AppImage (default: dist)
#   STEMFORGE_REQUIRE_FFMPEG=1  la build fallisce senza il FFmpeg LGPL
#                       (packaging/ffmpeg/out/linux-x64/ffmpeg): la
#                       release la imposta, letta da stemforge.spec
#   STEMFORGE_SKIP_SYSTEM_PACKAGES=1  non installare i pacchetti dnf
#                       (gia' presenti nell'immagine)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PYTHON="/opt/python/cp312-cp312/bin/python3.12"
GLIBC_REQUIRED="2.28"
LOCK="${STEMFORGE_LOCK:-$REPO/requirements-linux-x64.lock}"
WORK="${STEMFORGE_WORK:-$REPO/build/appimage}"
DIST="${STEMFORGE_DIST:-$REPO/dist}"
VENV="$WORK/venv"
APPDIR="$WORK/StemForge.AppDir"
TOOLS="$WORK/tools"

# Strumenti a versione fissa con SHA-256 (§2.2: la stessa build oggi e fra
# sei mesi). Il runtime e' scaricato a parte: senza --runtime-file
# appimagetool scaricherebbe "l'ultimo", cioe' un binario non verificato.
APPIMAGETOOL_VERSION="1.9.1"
APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/$APPIMAGETOOL_VERSION/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_VERSION="20251108"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_VERSION/runtime-x86_64"
RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"

# Python puro pubblicato solo come sorgente (allineato con
# SDIST_ALLOWLIST di packaging/gen_locks.py): si installa senza compilatore.
SDIST_ONLY="antlr4-python3-runtime,demucs,dora-search"
# torch "+cpu" esiste solo sull'indice di PyTorch; gli hash del lock
# impediscono che da qui arrivi un file diverso da quello fissato.
TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"

die() { echo "build_appimage.sh: ERRORE: $*" >&2; exit 1; }
log() { echo "build_appimage.sh: $*" >&2; }

check_environment() {
    [ "$(uname -m)" = "x86_64" ] || die "serve una macchina x86_64, questa e' $(uname -m)"
    local glibc
    glibc="$(getconf GNU_LIBC_VERSION | awk '{print $2}')"
    [ "$glibc" = "$GLIBC_REQUIRED" ] || die "glibc $glibc: la build va fatta in manylinux_2_28 (glibc $GLIBC_REQUIRED), vedi l'intestazione"
    [ -x "$PYTHON" ] || die "manca $PYTHON: non e' l'immagine manylinux_2_28"
    [ -f "$LOCK" ] || die "manca il lock $LOCK (lo genera packaging/gen_locks.py)"
}

# Il profilo e' solo CPU (decisione Fase 0): un torch CUDA porta ~3 GB di
# librerie nvidia e sfora il limite di 2 GB per file delle release.
check_lock_is_cpu_only() {
    if grep -Eiq '^nvidia-|^triton==' "$LOCK"; then
        die "il lock $LOCK contiene pacchetti CUDA (nvidia-*/triton): il profilo linux-x64 e' solo CPU"
    fi
    grep -Eq '^torch==[^ ]*\+cpu' "$LOCK" || die "nel lock $LOCK torch non e' la build +cpu"
}

# Le librerie X11 che Qt 6.7 carica e che una distribuzione desktop non
# installa sempre (libxcb-cursor0 su tutte). Servono qui perche'
# PyInstaller le copi nel pacchetto; quelle del sistema grafico (GL,
# libX11, fontconfig, wayland...) restano dell'host: host_libs.txt.
install_system_packages() {
    if [ "${STEMFORGE_SKIP_SYSTEM_PACKAGES:-0}" = "1" ]; then
        return
    fi
    log "pacchetti di sistema per il bundle"
    dnf -y -q install epel-release
    dnf -y -q install \
        xcb-util xcb-util-cursor xcb-util-image xcb-util-keysyms \
        xcb-util-renderutil xcb-util-wm libxkbcommon libxkbcommon-x11 \
        file desktop-file-utils
}

make_venv() {
    log "ambiente Python dal lock ($LOCK)"
    rm -rf "$VENV"
    "$PYTHON" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --no-input --disable-pip-version-check \
        --require-hashes --only-binary :all: --no-binary "$SDIST_ONLY" \
        --extra-index-url "$TORCH_CPU_INDEX" -r "$LOCK"
    "$VENV/bin/python" -m pip install --no-input --disable-pip-version-check \
        --only-binary :all: -r "$REPO/packaging/requirements-build.txt"
    if "$VENV/bin/python" -c "import av" 2>/dev/null; then
        die "PyAV e' nell'ambiente di build: il suo FFmpeg e' GPLv3 (D9)"
    fi
}

run_pyinstaller() {
    log "PyInstaller (profilo linux-x64)"
    (
        cd "$REPO"
        STEMFORGE_PROFILE=linux-x64 "$VENV/bin/python" -m PyInstaller \
            packaging/stemforge.spec --noconfirm --clean \
            --distpath "$WORK/dist" --workpath "$WORK/pyinstaller"
    )
    [ -x "$WORK/dist/StemForge/StemForge" ] || die "PyInstaller non ha prodotto dist/StemForge/StemForge"
}

make_appdir() {
    log "AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
        "$APPDIR/usr/share/icons/hicolor/256x256/apps"
    cp -a "$WORK/dist/StemForge" "$APPDIR/usr/lib/stemforge"
    "$VENV/bin/python" "$HERE/bundle_libs.py" "$APPDIR/usr/lib/stemforge" "$HERE/host_libs.txt" \
        --report "$WORK/system-libs.txt" >/dev/null
    install -m 0755 "$HERE/AppRun" "$APPDIR/AppRun"
    install -m 0644 "$HERE/stemforge.desktop" "$APPDIR/usr/share/applications/stemforge.desktop"
    ln -s usr/share/applications/stemforge.desktop "$APPDIR/stemforge.desktop"
    local icon="$APPDIR/usr/share/icons/hicolor/256x256/apps/stemforge.png"
    "$VENV/bin/python" - "$REPO/packaging/icon.png" "$icon" <<'PY'
import sys
from PIL import Image

ICON_SIZE = 256  # il formato piu' grande che ogni tema hicolor dichiara
Image.open(sys.argv[1]).resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS).save(sys.argv[2])
PY
    ln -s usr/share/icons/hicolor/256x256/apps/stemforge.png "$APPDIR/stemforge.png"
    ln -s stemforge.png "$APPDIR/.DirIcon"
    desktop-file-validate "$APPDIR/usr/share/applications/stemforge.desktop"
}

fetch_tool() {
    local url="$1" sha256="$2" target="$3"
    if [ ! -f "$target" ] || ! echo "$sha256  $target" | sha256sum -c --quiet - 2>/dev/null; then
        log "scarico $url"
        curl -fsSL --retry 3 -o "$target.part" "$url"
        echo "$sha256  $target.part" | sha256sum -c --quiet - || die "SHA-256 errato per $url"
        mv "$target.part" "$target"
    fi
    chmod +x "$target"
}

make_appimage() {
    local version output
    version="$("$VENV/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1]); import stemforge; print(stemforge.__version__)' "$REPO/src")"
    output="$DIST/StemForge-$version-linux-x86_64.AppImage"
    mkdir -p "$TOOLS" "$DIST"
    fetch_tool "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA256" "$TOOLS/appimagetool-$APPIMAGETOOL_VERSION.AppImage"
    fetch_tool "$RUNTIME_URL" "$RUNTIME_SHA256" "$TOOLS/runtime-$RUNTIME_VERSION-x86_64"
    log "appimagetool $APPIMAGETOOL_VERSION, runtime $RUNTIME_VERSION"
    rm -f "$output"
    # extract-and-run: nei container non c'e' FUSE. Nessuna informazione di
    # aggiornamento (-u/-g): niente auto-update (§0). -n: niente AppStream.
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 \
        "$TOOLS/appimagetool-$APPIMAGETOOL_VERSION.AppImage" -n \
        --runtime-file "$TOOLS/runtime-$RUNTIME_VERSION-x86_64" "$APPDIR" "$output"
    (cd "$DIST" && sha256sum "$(basename "$output")" > "$(basename "$output").sha256")
    # librerie di sistema entrate nel pacchetto, con rpm e licenza: la
    # materia prima di THIRD_PARTY_NOTICES per questo profilo (§11.11)
    cp "$WORK/system-libs.txt" "$DIST/StemForge-$version-linux-x86_64.libs.txt"
    log "AppImage: $output"
    cat "$output.sha256"
}

main() {
    check_environment
    check_lock_is_cpu_only
    install_system_packages
    mkdir -p "$WORK"
    make_venv
    run_pyinstaller
    make_appdir
    make_appimage
}

main "$@"
