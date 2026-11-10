#!/usr/bin/env bash
# FFmpeg minimo LGPL per StemForge (BUILD_SPEC D9, §2.2, §9.1).
#
#   packaging/ffmpeg/build.sh <legacy-intel|mac-arm64|linux-x64|win-x64>
#
# Produce packaging/ffmpeg/out/<profilo>/ffmpeg[.exe] e lo verifica:
# configurazione senza --enable-gpl/--enable-nonfree/--enable-version3,
# licenza dichiarata LGPL 2.1+, dipendenze dinamiche solo di sistema,
# sistema minimo rispettato (macOS 10.15/11.0, glibc 2.28).
#
# Dove gira ogni profilo (contratto con la CI, vedi README.md):
#   legacy-intel  runner macOS (Intel, o arm64 con cross-compilazione)
#   mac-arm64     runner macOS (arm64, o Intel con cross-compilazione)
#   linux-x64     dentro quay.io/pypa/manylinux_2_28_x86_64 (lo script ci
#                 rientra da solo con docker se lanciato fuori)
#   win-x64       Linux con mingw-w64 (cross-compilazione), poi
#                 check_license.sh sul runner Windows
#
# Variabili facoltative:
#   FFMPEG_WORK_DIR    dove scaricare e compilare (default: build/ qui accanto)
#   FFMPEG_JOBS        parallelismo di make
#   MINGW_PREFIX       prefisso del cross-compilatore win-x64 (x86_64-w64-mingw32-)
#   FFMPEG_CC          compilatore C esplicito (es. per llvm-mingw)
#   MANYLINUX_IMAGE    immagine per linux-x64 (fissarla per digest in CI)
#   STEMFORGE_FFMPEG_ALLOW_HOST_GLIBC=1  SOLO sviluppo: linux-x64 fuori da
#                      manylinux; il binario richiede la glibc dell'host
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PROFILE="${1:-}"
VERSION="$(tr -d ' \r\n' < "$HERE/VERSION")"
TARBALL="ffmpeg-$VERSION.tar.xz"
URL="https://ffmpeg.org/releases/$TARBALL"
WORK="${FFMPEG_WORK_DIR:-$HERE/build}"
OUT="$HERE/out/$PROFILE"
GLIBC_MAX="2.28"
MANYLINUX_IMAGE="${MANYLINUX_IMAGE:-quay.io/pypa/manylinux_2_28_x86_64}"

die() { echo "build.sh: ERRORE: $*" >&2; exit 1; }
log() { echo "build.sh: $*" >&2; }

# Solo cio' che serve a StemForge: decodifica dei formati audio comuni,
# piu' gli encoder/muxer con cui i test generano i propri fixture.
# Niente di GPL, niente di "nonfree", niente librerie esterne.
COMMON_FLAGS=(
  --disable-everything --disable-autodetect --disable-network --disable-doc
  --disable-ffplay --disable-ffprobe --enable-ffmpeg
  --disable-avdevice --disable-swscale --disable-postproc
  --enable-avcodec --enable-avformat --enable-avfilter --enable-swresample
  --enable-static --disable-shared --enable-small --disable-debug
  # i decoder audio in C bastano (decine di volte il tempo reale anche sul
  # Mac del 2012) e cosi' nessun profilo dipende da nasm
  --disable-x86asm
  --enable-protocol=file,pipe
  --enable-demuxer=mov,mp3,aac,ogg,flac,wav,aiff,matroska,w64,caf
  --enable-decoder='aac,aac_latm,alac,mp3,mp3float,vorbis,opus,flac,pcm_*'
  --enable-parser=aac,aac_latm,mpegaudio,vorbis,opus,flac
  --enable-encoder=pcm_f32le,pcm_s16le,pcm_s24le,aac,alac,flac
  # "-f f32le" in configure si chiama pcm_f32le: col nome corto configure
  # tace e il muxer resta spento (lo scopre REQUIRED_CONFIG)
  --enable-muxer=wav,ipod,mp4,caf,flac,pcm_f32le
  --enable-filter=aresample,aformat,anull
)

# Componenti che devono risultare accesi dopo configure: --disable-autodetect
# spegne in silenzio cio' che manca di dipendenze (es. i thread, senza i
# quali dalla 7.0 il programma ffmpeg non viene costruito affatto).
REQUIRED_CONFIG=(
  CONFIG_FFMPEG CONFIG_SWRESAMPLE CONFIG_AVFILTER
  CONFIG_FILE_PROTOCOL CONFIG_PIPE_PROTOCOL
  CONFIG_MOV_DEMUXER CONFIG_MP3_DEMUXER CONFIG_AAC_DEMUXER CONFIG_OGG_DEMUXER
  CONFIG_FLAC_DEMUXER CONFIG_WAV_DEMUXER CONFIG_AIFF_DEMUXER
  CONFIG_MATROSKA_DEMUXER CONFIG_W64_DEMUXER CONFIG_CAF_DEMUXER
  CONFIG_AAC_DECODER CONFIG_AAC_LATM_DECODER CONFIG_ALAC_DECODER
  CONFIG_MP3_DECODER CONFIG_MP3FLOAT_DECODER CONFIG_VORBIS_DECODER
  CONFIG_OPUS_DECODER CONFIG_FLAC_DECODER CONFIG_PCM_S16LE_DECODER
  CONFIG_PCM_S24BE_DECODER CONFIG_PCM_F32LE_DECODER
  CONFIG_AAC_PARSER CONFIG_MPEGAUDIO_PARSER CONFIG_FLAC_PARSER
  CONFIG_PCM_F32LE_ENCODER CONFIG_PCM_S16LE_ENCODER CONFIG_PCM_S24LE_ENCODER
  CONFIG_AAC_ENCODER CONFIG_ALAC_ENCODER CONFIG_FLAC_ENCODER
  CONFIG_WAV_MUXER CONFIG_IPOD_MUXER CONFIG_MP4_MUXER CONFIG_CAF_MUXER
  CONFIG_FLAC_MUXER CONFIG_PCM_F32LE_MUXER
  CONFIG_ARESAMPLE_FILTER CONFIG_AFORMAT_FILTER CONFIG_ANULL_FILTER
)
FORBIDDEN_CONFIG=(CONFIG_GPL CONFIG_NONFREE CONFIG_VERSION3)

usage() {
  echo "uso: $0 <legacy-intel|mac-arm64|linux-x64|win-x64>" >&2
  exit 2
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

fetch_source() {
  local expected tarball="$WORK/$TARBALL"
  expected="$(cut -d' ' -f1 < "$HERE/SOURCE_SHA256" | tr -d '\r\n')"
  mkdir -p "$WORK"
  if [ ! -f "$tarball" ]; then
    log "scarico $URL"
    curl -fL --retry 3 -o "$tarball.part" "$URL"
    mv "$tarball.part" "$tarball"
  fi
  if [ "$(sha256_of "$tarball")" != "$expected" ]; then
    rm -f "$tarball"
    die "SHA-256 di $TARBALL diverso da SOURCE_SHA256: sorgente rifiutato"
  fi
  log "sorgente verificato: $TARBALL sha256=$expected"
  rm -rf "$WORK/ffmpeg-$VERSION"
  tar -xJf "$tarball" -C "$WORK"
}

# --- profili ----------------------------------------------------------------

macos_flags() {  # $1 arch FFmpeg, $2 arch clang, $3 macOS minimo
  export MACOSX_DEPLOYMENT_TARGET="$3"
  local mflags="-arch $2 -mmacosx-version-min=$3"
  PROFILE_FLAGS=(--arch="$1" --target-os=darwin --cc=clang --enable-pthreads
    --extra-cflags="$mflags" --extra-ldflags="$mflags")
  if [ "$(uname -m)" != "$2" ]; then PROFILE_FLAGS+=(--enable-cross-compile); fi
  EXE="ffmpeg"
}

linux_flags() {
  [ "$(uname -s)" = Linux ] || die "linux-x64 si compila su Linux (manylinux_2_28)"
  PROFILE_FLAGS=(--arch=x86_64 --target-os=linux --enable-pthreads)
  EXE="ffmpeg"
}

win_flags() {
  local prefix="${MINGW_PREFIX:-x86_64-w64-mingw32-}"
  # w32threads invece di pthreads e -static: nessuna DLL di MinGW da
  # portarsi dietro (libwinpthread, libgcc_s)
  PROFILE_FLAGS=(--arch=x86_64 --target-os=mingw32 --enable-cross-compile
    --cross-prefix="$prefix" --enable-w32threads --extra-ldflags=-static)
  command -v "${FFMPEG_CC:-${prefix}gcc}" >/dev/null 2>&1 \
    || die "compilatore ${FFMPEG_CC:-${prefix}gcc} assente (apt install mingw-w64)"
  EXE="ffmpeg.exe"
}

select_profile() {
  case "$PROFILE" in
    legacy-intel) macos_flags x86_64 x86_64 10.15 ;;
    mac-arm64)    macos_flags aarch64 arm64 11.0 ;;
    linux-x64)    linux_flags ;;
    win-x64)      win_flags ;;
    *) usage ;;
  esac
  if [ -n "${FFMPEG_CC:-}" ]; then PROFILE_FLAGS+=(--cc="$FFMPEG_CC"); fi
}

# linux-x64 deve nascere con glibc 2.28: fuori da manylinux si rientra in
# docker, salvo l'eccezione dichiarata per lo sviluppo.
maybe_enter_manylinux() {
  [ "$PROFILE" = linux-x64 ] || return 0
  case "${AUDITWHEEL_PLAT:-}" in manylinux_2_28_*) return 0 ;; esac
  if [ "${STEMFORGE_FFMPEG_ALLOW_HOST_GLIBC:-}" = 1 ]; then
    log "ATTENZIONE: build fuori da manylinux_2_28, solo per sviluppo"
    return 0
  fi
  command -v docker >/dev/null 2>&1 \
    || die "linux-x64 va compilato in manylinux_2_28 e docker non c'e'"
  log "rientro in $MANYLINUX_IMAGE"
  exec docker run --rm -v "$REPO:/repo" -w /repo \
    -e FFMPEG_JOBS -e FFMPEG_WORK_DIR=/repo/packaging/ffmpeg/build \
    "$MANYLINUX_IMAGE" bash /repo/packaging/ffmpeg/build.sh linux-x64
}

# --- configure, make, controlli ---------------------------------------------

refuse_license_flags() {
  local flag
  for flag in "$@"; do
    case "$flag" in
      --enable-gpl|--enable-nonfree|--enable-version3|--enable-lib*)
        die "flag vietato da D9: $flag" ;;
    esac
  done
}

check_config_headers() {  # $1 cartella di build
  local name
  for name in "${REQUIRED_CONFIG[@]}"; do
    grep -qE "^#define $name 1\$" "$1/config.h" "$1/config_components.h" \
      || die "configure ha spento $name (dipendenza mancante?)"
  done
  for name in "${FORBIDDEN_CONFIG[@]}"; do
    grep -qE "^#define $name 0\$" "$1/config.h" || die "$name acceso: non LGPL"
  done
}

configure_and_make() {
  local obj="$WORK/obj-$PROFILE"
  local jobs="${FFMPEG_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
  refuse_license_flags "${COMMON_FLAGS[@]}" "${PROFILE_FLAGS[@]}"
  rm -rf "$obj" && mkdir -p "$obj"
  log "configure ($PROFILE): ${COMMON_FLAGS[*]} ${PROFILE_FLAGS[*]}"
  (cd "$obj" && "$WORK/ffmpeg-$VERSION/configure" \
    "${COMMON_FLAGS[@]}" "${PROFILE_FLAGS[@]}") \
    || { tail -n 40 "$obj/ffbuild/config.log" >&2 || true; die "configure fallito"; }
  check_config_headers "$obj"
  make -C "$obj" -j"$jobs" "$EXE"
  mkdir -p "$OUT"
  cp "$obj/$EXE" "$OUT/$EXE"
  cp "$WORK/ffmpeg-$VERSION/COPYING.LGPLv2.1" "$OUT/COPYING.LGPLv2.1"
  printf 'FFmpeg %s (LGPL 2.1+)\nsorgente: %s\nsha256: %s\n' "$VERSION" "$URL" \
    "$(cut -d' ' -f1 < "$HERE/SOURCE_SHA256")" > "$OUT/SOURCE.txt"
}

# Si puo' eseguire il binario qui? Se si', il controllo di licenza e' a
# runtime ed e' obbligatorio; altrimenti statico, e quello a runtime lo fa
# il job nativo (es. win-x64 sul runner Windows).
can_run_target() {
  case "$PROFILE" in
    linux-x64) return 0 ;;
    win-x64) "$OUT/$EXE" -hide_banner -version >/dev/null 2>&1 ;;
    legacy-intel) [ "$(uname -m)" = x86_64 ] || arch -x86_64 /usr/bin/true 2>/dev/null ;;
    mac-arm64) [ "$(uname -m)" = arm64 ] ;;
  esac
}

check_linux_deps() {  # $1 binario
  local newest needed
  # solo la glibc: qualunque altra .so mancherebbe su qualche distribuzione
  needed="$(readelf -d "$1" | grep NEEDED \
    | grep -vE '\[(libc|libm|libpthread|libdl|librt)\.so\.[0-9]+\]|\[ld-linux-x86-64\.so\.2\]' \
    || true)"
  [ -z "$needed" ] || die "dipendenze dinamiche oltre la glibc: $needed"
  newest="$(objdump -T "$1" | grep -oE 'GLIBC_[0-9.]+' | cut -d_ -f2 | sort -V | tail -n1)"
  log "glibc richiesta: $newest"
  if [ "$(printf '%s\n%s\n' "$newest" "$GLIBC_MAX" | sort -V | tail -n1)" != "$GLIBC_MAX" ] \
    && [ "${STEMFORGE_FFMPEG_ALLOW_HOST_GLIBC:-}" != 1 ]; then
    die "il binario richiede glibc $newest > $GLIBC_MAX"
  fi
}

check_win_deps() {  # $1 binario
  local objdump="${MINGW_PREFIX:-x86_64-w64-mingw32-}objdump" dlls
  command -v "$objdump" >/dev/null 2>&1 || objdump=objdump
  dlls="$("$objdump" -p "$1" | grep -i 'DLL Name' | awk '{print $3}')"
  log "DLL importate: $(printf '%s ' $dlls)"
  # le DLL di MinGW (libwinpthread-1, libgcc_s_seh-1, libstdc++-6) non
  # esistono sul PC dell'utente: con -static non devono comparire
  if printf '%s\n' "$dlls" | grep -iE '^lib[a-z0-9_+-]*\.dll$'; then
    die "ffmpeg.exe dipende da DLL non di sistema"
  fi
}

check_dependencies() {
  local bin="$OUT/$EXE"
  case "$PROFILE" in
    linux-x64) check_linux_deps "$bin" ;;
    win-x64) check_win_deps "$bin" ;;
    legacy-intel|mac-arm64)
      if otool -L "$bin" | tail -n +2 | grep -vE '^[[:space:]]+(/usr/lib/|/System/)'; then
        die "ffmpeg dipende da librerie fuori dal sistema"
      fi
      python3 "$REPO/packaging/macos/check_min_os.py" "$OUT" "$MACOSX_DEPLOYMENT_TARGET" ;;
  esac
}

pick_work_dir() {
  # configure di FFmpeg rifiuta percorsi con spazi
  case "$WORK" in
    *[[:space:]]*)
      [ -z "${FFMPEG_WORK_DIR:-}" ] || die "FFMPEG_WORK_DIR non puo' contenere spazi"
      WORK="${TMPDIR:-/tmp}/stemforge-ffmpeg-build"
      log "percorso del repo con spazi: compilo in $WORK" ;;
  esac
}

main() {
  [ -n "$PROFILE" ] || usage
  pick_work_dir
  select_profile
  maybe_enter_manylinux
  fetch_source
  configure_and_make
  check_dependencies
  if can_run_target; then
    bash "$HERE/check_license.sh" "$OUT/$EXE"
  else
    log "binario non eseguibile su questo host: controllo statico"
    bash "$HERE/check_license.sh" --static "$OUT/$EXE"
  fi
  log "fatto: $OUT/$EXE"
}

main
