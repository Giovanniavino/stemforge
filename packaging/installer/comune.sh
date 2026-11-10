# Passi comuni di "Installa StemForge.command" e "Aggiorna StemForge.command"
# (BUILD_SPEC §9.5). Non si lancia da solo: lo caricano i due script con
# ". comune.sh" dopo aver definito die() e SRC_DIR.
#
# Stare in un solo file e' il punto: i due script prima divergevano (uno
# installava dal lock con gli hash, l'altro no) e Aggiorna restava indietro
# ogni volta che il lock cambiava.

BUILD_ENV="$HOME/Library/Application Support/StemForge/build-env"
PYBIN="$BUILD_ENV/bin/python"
APP_DEST="/Applications/StemForge.app"
# Python puro pubblicato solo come sdist: si installa senza compilatore.
# Allineato con SDIST_ALLOWLIST in packaging/gen_locks.py.
SDIST_ONLY="antlr4-python3-runtime,demucs,dora-search"
# Il FFmpeg LGPL (D9) del Mac mini sta dove lo spec lo cerca per il
# profilo legacy-intel: make_installer.py lo mette li' nello zip.
FFMPEG_BIN="$SRC_DIR/packaging/ffmpeg/out/legacy-intel/ffmpeg"
FFMPEG_STATUS="assente"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# Un avviso che deve restare in vista anche dopo centinaia di righe di pip.
warn_box() {
    printf '\n\033[33m\033[1m!!! ATTENZIONE !!!\033[0m\n\033[33m%s\033[0m\n' "$1"
}

# Installa (o completa) l'ambiente dai lock con gli hash. pip salta cio'
# che e' gia' presente alla versione giusta: in un aggiornamento scarica
# solo quello che il lock nuovo aggiunge o cambia.
install_locked_deps() {
    lock="$SRC_DIR/requirements-macos-x86_64.lock"
    build_lock="$SRC_DIR/packaging/installer/requirements-build-macos-x86_64.lock"
    for file in "$lock" "$build_lock"; do
        [ -f "$file" ] || die "file mancante: $file
il pacchetto e' incompleto: riscarica lo zip ed estrailo TUTTO."
    done
    # --only-binary :all: = questo Mac non deve MAI compilare codice nativo.
    "$PYBIN" -m pip install --require-hashes \
        --only-binary :all: --no-binary "$SDIST_ONLY" -r "$lock" \
        || die "installazione delle dipendenze non riuscita.
Se vedi errori di rete, controlla la connessione e rilancia.
Se vedi 'Building wheel' o errori di compilazione, NON e' colpa tua:
manda a chi ti ha dato questo pacchetto le ultime 30 righe qui sopra."
    "$PYBIN" -m pip install --quiet --require-hashes --only-binary :all: -r "$build_lock" \
        || die "strumenti di costruzione non installabili (probabile problema di rete: riprova)."
    # PyAV porta un FFmpeg GPLv3 (D9): il lock non lo contiene piu', ma un
    # ambiente creato prima puo' averlo ancora. Lo spec lo esclude comunque.
    if "$PYBIN" -m pip show av >/dev/null 2>&1; then
        "$PYBIN" -m pip uninstall --quiet --yes av \
            || die "non riesco a togliere PyAV dall'ambiente: rifai l'installazione completa."
    fi
    "$PYBIN" -m pip install --quiet "$SRC_DIR" --no-deps --no-build-isolation --force-reinstall \
        || die "installazione di StemForge dai sorgenti non riuscita: manda le righe qui sopra a chi ti ha dato il pacchetto."
}

# Prepara il FFmpeg incluso nello zip: eseguibile, senza quarantena e
# provato su QUESTO Mac. Uno che non parte viene messo da parte, cosi' lo
# spec non lo impacchetta e l'app dice "formato non supportato" invece di
# fallire a meta' lettura.
prepare_ffmpeg() {
    if [ ! -f "$FFMPEG_BIN" ]; then
        # gia' provato e scartato da un giro precedente con questo zip
        if [ -f "$FFMPEG_BIN.non-parte" ]; then
            FFMPEG_STATUS="non parte"
        else
            FFMPEG_STATUS="assente"
        fi
        return 0
    fi
    chmod 755 "$FFMPEG_BIN"
    # la quarantena dello zip scaricato farebbe bloccare a Gatekeeper la prova qui sotto
    xattr -d com.apple.quarantine "$FFMPEG_BIN" 2>/dev/null || true
    if "$FFMPEG_BIN" -hide_banner -version >/dev/null 2>&1; then
        FFMPEG_STATUS="ok"
        echo "    FFmpeg LGPL incluso: m4a/aac/alac saranno supportati."
    else
        mv -f "$FFMPEG_BIN" "$FFMPEG_BIN.non-parte"
        FFMPEG_STATUS="non parte"
    fi
}

# Costruisce l'app col profilo legacy-intel (BUILD_SPEC §2): dichiarato e
# non dedotto, perche' sotto Rosetta "la macchina" e' ambigua.
build_app() {
    cd "$SRC_DIR/packaging" || die "cartella packaging mancante in $SRC_DIR."
    rm -rf build dist
    STEMFORGE_PROFILE=legacy-intel "$BUILD_ENV/bin/pyinstaller" stemforge.spec \
        --noconfirm --log-level ERROR \
        || die "costruzione dell'app non riuscita: manda le righe qui sopra a chi ti ha dato il pacchetto."
    [ -d "dist/StemForge.app" ] || die "l'app non risulta costruita."
    if [ "$FFMPEG_STATUS" = "ok" ] && [ -z "$(find dist/StemForge.app -type f -path '*/ffmpeg/ffmpeg' -perm -u+x)" ]; then
        FFMPEG_STATUS="non impacchettato"
    fi
}

copy_to_applications() {
    rm -rf "$APP_DEST"
    ditto "dist/StemForge.app" "$APP_DEST" || die "copia in /Applications non riuscita."
    rm -rf build dist
}

# Mai un errore muto: se m4a/aac non funzioneranno, lo si dice adesso.
ffmpeg_notice() {
    case "$FFMPEG_STATUS" in
        ok) return 0 ;;
        assente) reason="lo zip non contiene il decoder FFmpeg" ;;
        "non parte") reason="il decoder FFmpeg incluso non parte su questo Mac" ;;
        *) reason="il decoder FFmpeg non e' entrato nell'app" ;;
    esac
    warn_box "StemForge funziona, ma NON aprira' i file m4a, aac e alac:
$reason.
I file wav, flac, mp3, ogg e aiff funzionano normalmente.
Per avere anche m4a/aac chiedi a chi ti ha dato StemForge uno zip con
FFmpeg incluso, poi usa \"Aggiorna StemForge.command\"."
}
