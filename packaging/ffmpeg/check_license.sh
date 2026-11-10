#!/usr/bin/env bash
# Verifica che un binario ffmpeg sia LGPL (BUILD_SPEC D9).
#
#   packaging/ffmpeg/check_license.sh [--static] <ffmpeg[.exe]>
#
# Di default ESEGUE il binario: "ffmpeg -version" non deve mostrare
# --enable-gpl, --enable-nonfree o --enable-version3, e "ffmpeg -L" deve
# dichiarare la GNU Lesser General Public License 2.1 o successiva.
# Con --static (binario di un'altra piattaforma, es. ffmpeg.exe compilato
# su Linux) legge le stesse informazioni dalle stringhe incise nel binario;
# il controllo a runtime va poi ripetuto sulla piattaforma vera (CI).
# Esce con 0 solo se tutto torna; stampa la configurazione trovata.
set -euo pipefail

FORBIDDEN_RE='--enable-(gpl|nonfree|version3)([[:space:]]|$)'

fail() { echo "check_license: NON CONFORME: $*" >&2; exit 1; }

runtime_check() {
  local bin="$1" version license config
  version="$("$bin" -hide_banner -version)" || fail "$bin non si esegue"
  license="$("$bin" -hide_banner -L)" || fail "$bin -L fallito"
  config="$(printf '%s\n' "$version" | grep '^configuration:' || true)"
  [ -n "$config" ] || fail "nessuna riga 'configuration:' in -version"
  printf '%s\n' "$version" | head -n1
  printf '%s\n' "$config"
  if printf '%s\n' "$config" | grep -qE -- "$FORBIDDEN_RE"; then
    fail "configurazione con flag GPL/nonfree/version3"
  fi
  # -L di un build GPL dice "GNU General Public License"; quello LGPL
  # "GNU Lesser General Public License ... version 2.1". Il testo va a capo
  # a meta' frase, e ffmpeg.exe (anche lanciato da WSL) termina le righe
  # con CRLF: si normalizza tutto a spazi singoli prima di cercare.
  license="$(printf '%s\n' "$license" | tr '\r\n' '  ' | tr -s ' ')"
  printf '%s\n' "$license" | grep -q 'GNU Lesser General Public License' \
    || fail "-L non dichiara la GNU Lesser General Public License"
  printf '%s\n' "$license" | grep -q 'version 2\.1 of the License' \
    || fail "-L non dichiara la versione 2.1"
  if printf '%s\n' "$license" | grep -q 'GNU General Public License'; then
    fail "-L dichiara la GPL"
  fi
  echo "licenza: LGPL 2.1 o successiva (verificata eseguendo -L)"
}

static_check() {
  local bin="$1" licenses config
  # FFMPEG_LICENSE ("LGPL version 2.1 or later") e FFMPEG_CONFIGURATION
  # sono stringhe costanti nel binario: sono quelle che stampano -L/-version
  licenses="$(grep -aoE '[A-Za-z]*GPL version [0-9.]+ or later' "$bin" | sort -u)"
  [ "$licenses" = "LGPL version 2.1 or later" ] \
    || fail "stringhe di licenza inattese: ${licenses:-nessuna}"
  config="$(grep -aoE -- '[^[:cntrl:]]*--disable-everything[^[:cntrl:]]*' "$bin" \
    | head -n1 || true)"
  [ -n "$config" ] || fail "stringa di configurazione non trovata nel binario"
  echo "configuration: $config"
  if printf '%s\n' "$config" | grep -qE -- "$FORBIDDEN_RE"; then
    fail "configurazione con flag GPL/nonfree/version3"
  fi
  echo "licenza: $licenses (controllo statico: ripetere a runtime sulla piattaforma)"
}

main() {
  local mode=runtime
  if [ "${1:-}" = --static ]; then mode=static; shift; fi
  [ $# -eq 1 ] || { echo "uso: $0 [--static] <ffmpeg>" >&2; exit 2; }
  [ -f "$1" ] || fail "$1 non esiste"
  "${mode}_check" "$1"
}

main "$@"
