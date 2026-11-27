#!/usr/bin/env bash
# Collaudo dell'AppImage cosi' come la riceve l'utente (BUILD_SPEC §9.6, §10.5).
#
#   packaging/linux/test_appimage.sh StemForge-X.Y.Z-linux-x86_64.AppImage REPORT.json [--offline]
#
# Gira come root in un container Ubuntu pulito (CI: `container: ubuntu:20.04`
# e `ubuntu:24.04`; dev-box: rootless_container.py). Tre passi:
# 1. installa SOLO le librerie che l'AppImage lascia all'host
#    (host_libs.txt): cio' che ogni desktop Linux ha gia'. Niente Python,
#    niente certificati di sistema: se l'AppImage ne avesse bisogno, il
#    collaudo deve fallire qui e non sulla macchina dell'utente;
# 2. controlla che i plugin di piattaforma Qt (xcb, wayland) trovino
#    tutte le loro librerie: in un container senza schermo il selftest usa
#    "offscreen", quindi un libxcb-cursor mancante non lo vedrebbe;
# 3. lancia `--selftest --report` con QT_QPA_PLATFORM=offscreen.
# Senza FUSE (il caso dei container) si usa --appimage-extract-and-run.
set -euo pipefail

die() { echo "test_appimage.sh: ERRORE: $*" >&2; exit 1; }
log() { echo "test_appimage.sh: $*" >&2; }

[ $# -ge 2 ] || die "uso: $0 APPIMAGE REPORT.json [--offline]"
APPIMAGE_FILE="$(readlink -f "$1")"
REPORT="$2"
shift 2
[ -f "$APPIMAGE_FILE" ] || die "AppImage non trovata: $APPIMAGE_FILE"

# Le librerie di host_libs.txt, per nome di pacchetto Ubuntu 20.04. Su
# 24.04 alcune hanno il suffisso t64 (transizione time_t a 64 bit) e il
# vecchio nome e' solo virtuale: "no installation candidate" (collaudo del
# 26-11-2026). install_host_libraries sceglie il nome che esiste.
HOST_PACKAGES=(
    libgl1 libegl1 libopengl0 libdrm2 libgbm1
    libx11-6 libx11-xcb1 libxcb1
    libfontconfig1 libfreetype6
    libwayland-client0 libwayland-cursor0 libwayland-egl1
    libdbus-1-3 libglib2.0-0
    libpulse0 libasound2
    zlib1g libzstd1
)

install_host_libraries() {
    if [ "${STEMFORGE_SKIP_HOST_PACKAGES:-0}" = "1" ]; then
        return
    fi
    log "librerie dell'host (quelle di un desktop qualsiasi)"
    export DEBIAN_FRONTEND=noninteractive
    local -a apt_options=()
    # Namespace utente con il solo root mappato (rootless_container.py sul
    # dev-box): nessun altro utente o gruppo esiste. apt non puo' cedere i
    # download all'utente _apt ("seteuid failed"), e il postinst di
    # fontconfig-config fa chown root:staff sulla cartella dei font locali
    # solo se la crea lui (visto il 20-11-2026). In CI (root vero) nulla.
    if [ "$(awk '{n++; size=$3} END {print n ":" size}' /proc/self/uid_map)" = "1:1" ]; then
        apt_options=(-o APT::Sandbox::User=root)
        mkdir -p /usr/local/share/fonts
    fi
    apt-get "${apt_options[@]}" update -qq
    local i
    for i in "${!HOST_PACKAGES[@]}"; do
        if apt-cache show "${HOST_PACKAGES[$i]}t64" >/dev/null 2>&1; then
            HOST_PACKAGES[i]+="t64"
        fi
    done
    apt-get "${apt_options[@]}" install -y -qq --no-install-recommends "${HOST_PACKAGES[@]}"
}

# Ogni libreria dei plugin di piattaforma deve risolversi nel pacchetto o
# fra quelle dell'host installate sopra. Stesso LD_LIBRARY_PATH che
# imposta il bootloader di PyInstaller.
check_platform_plugins() {
    local root="$1" internal plugins missing="" plugin found=0
    internal="$root/usr/lib/stemforge/_internal"
    plugins="$internal/PySide6/Qt/plugins"
    for plugin in "$plugins"/platforms/libqxcb.so "$plugins"/platforms/libqwayland*.so \
        "$plugins"/wayland-shell-integration/*.so "$plugins"/xcbglintegrations/*.so; do
        [ -f "$plugin" ] || continue
        found=$((found + 1))
        missing+="$(LD_LIBRARY_PATH="$internal" ldd "$plugin" | awk -v p="${plugin##*/}" '/not found/ {print "  " p ": " $1}')"
    done
    [ -f "$plugins/platforms/libqxcb.so" ] || die "plugin xcb assente dal pacchetto"
    [ -z "$missing" ] || die "librerie mancanti per i plugin Qt:"$'\n'"$missing"
    log "plugin di piattaforma Qt: $found, tutte le dipendenze risolte"
}

run_selftest() {
    local -a launch=("$APPIMAGE_FILE")
    if [ ! -e /dev/fuse ] || ! { command -v fusermount3 || command -v fusermount; } >/dev/null 2>&1; then
        launch+=(--appimage-extract-and-run)
    fi
    log "selftest: ${launch[*]} --selftest --report $REPORT $*"
    local status=0
    QT_QPA_PLATFORM=offscreen "${launch[@]}" --selftest --report "$REPORT" "$@" || status=$?
    [ -f "$REPORT" ] || die "nessun report prodotto (uscita $status)"
    # la chiave di primo livello (json.dumps indent=2), non un "ok" dentro
    # il dettaglio di un controllo: qui non c'e' Python per leggere il JSON
    grep -Eq '^  "ok": true,$' "$REPORT" || die "selftest fallito (uscita $status), vedi $REPORT"
    [ "$status" -eq 0 ] || die "selftest riuscito ma uscita $status"
    log "COLLAUDO RIUSCITO"
}

main() {
    install_host_libraries
    # globale, non local: la trap gira a fine script, fuori da main
    SCRATCH="$(mktemp -d)"
    trap 'rm -rf "$SCRATCH"' EXIT
    chmod +x "$APPIMAGE_FILE"
    (cd "$SCRATCH" && "$APPIMAGE_FILE" --appimage-extract >/dev/null)
    check_platform_plugins "$SCRATCH/squashfs-root"
    run_selftest "$@"
}

main "$@"
