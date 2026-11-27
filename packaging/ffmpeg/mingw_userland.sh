#!/usr/bin/env bash
# Cross-compilatore mingw-w64 per il profilo win-x64 SENZA root, per il
# dev-box (WSL2 Ubuntu) dove "apt install" chiederebbe la password.
#
#   packaging/ffmpeg/mingw_userland.sh <cartella>
#   eval "$(packaging/ffmpeg/mingw_userland.sh ~/.cache/stemforge-dev/mingw)"
#   packaging/ffmpeg/build.sh win-x64
#
# Scarica con "apt-get download" (firma dell'archivio Ubuntu verificata da
# apt) gli stessi pacchetti che la CI installa con
# "apt-get install gcc-mingw-w64-x86-64-win32", li estrae in <cartella> e
# stampa gli export per build.sh. Nessun file di sistema viene toccato.
# Variante "win32" dei thread: nessuna libwinpthread da distribuire.
set -euo pipefail

DEST="${1:?uso: $0 <cartella>}"
PACKAGES=(
  binutils-mingw-w64-x86-64
  gcc-mingw-w64-base
  gcc-mingw-w64-x86-64-win32
  gcc-mingw-w64-x86-64-win32-runtime
  mingw-w64-common
  mingw-w64-x86-64-dev
)

mkdir -p "$DEST/debs"
if [ ! -x "$DEST/usr/bin/x86_64-w64-mingw32-gcc-win32" ]; then
  (cd "$DEST/debs" && apt-get download "${PACKAGES[@]}") >&2
  for deb in "$DEST"/debs/*.deb; do dpkg-deb -x "$deb" "$DEST"; done
fi
# il link x86_64-w64-mingw32-gcc lo crea update-alternatives all'installazione:
# estraendo a mano c'e' solo il nome con il suffisso della variante
ln -sf x86_64-w64-mingw32-gcc-win32 "$DEST/usr/bin/x86_64-w64-mingw32-gcc"
# dal PATH e col prefisso di default, non per percorso assoluto: configure
# incide i suoi argomenti nel binario ("ffmpeg -version", license_info),
# e la cartella home dello sviluppatore non deve finirci
echo "export PATH='$DEST/usr/bin':\"\$PATH\""
