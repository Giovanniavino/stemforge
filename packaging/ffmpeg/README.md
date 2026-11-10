# FFmpeg LGPL minimo (BUILD_SPEC D9)

StemForge decodifica m4a/aac/alac (e il resto che soundfile non legge)
con un `ffmpeg` compilato qui: sorgente ufficiale a versione fissa,
configurazione LGPL 2.1+, nessuna libreria esterna. L'app lo lancia come
processo separato (`src/stemforge/engine/ffmpeg.py`), senza linking.

| File | Contenuto |
|---|---|
| `VERSION` | versione del sorgente (serie 7.1, ultima patch) |
| `SOURCE_SHA256` | SHA-256 del tarball, formato `sha256sum` |
| `build.sh <profilo>` | scarica, verifica, configura, compila, controlla |
| `check_license.sh [--static] <bin>` | licenza e configurazione di un binario |
| `mingw_userland.sh <dir>` | cross-compilatore mingw-w64 senza root (dev-box WSL) |

## Sorgente

`https://ffmpeg.org/releases/ffmpeg-<VERSION>.tar.xz`. ffmpeg.org non
pubblica SHA-256 ma una firma GPG (`.asc`): l'hash in `SOURCE_SHA256` è
stato calcolato sul tarball scaricato **dopo** aver verificato la firma
con la chiave di release FFmpeg
`FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8`
(`https://ffmpeg.org/ffmpeg-devel.asc`). Per aggiornare la patch: nuova
versione in `VERSION`, firma verificata, nuovo hash in `SOURCE_SHA256`.
`build.sh` rifiuta qualunque tarball con hash diverso.

## Configurazione

`--disable-everything --disable-autodetect --disable-network --disable-doc`,
solo il programma `ffmpeg`, protocolli `file`/`pipe`; demuxer, decoder,
parser, encoder (per i fixture dei test), muxer e filtri audio elencati
in `COMMON_FLAGS` di `build.sh`; librerie FFmpeg statiche, `--enable-small`.
**Mai** `--enable-gpl`, `--enable-nonfree`, `--enable-version3` né
`--enable-lib*`: `build.sh` li rifiuta prima di configure, poi controlla
`config.h` (`CONFIG_GPL/NONFREE/VERSION3 0`) e che ogni componente
richiesto sia davvero acceso (configure spegne in silenzio ciò che non
riconosce o che non ha dipendenze).

A fine build `check_license.sh` esegue `ffmpeg -version` (nessun flag
vietato nella riga `configuration:`) e `ffmpeg -L` (deve dichiarare la
GNU Lesser General Public License 2.1). Se il binario non si può eseguire
sull'host di build, il controllo è statico sulle stringhe incise nel
binario e va ripetuto a runtime sulla piattaforma vera.

## Contratto con la CI (area G)

Uscita: `packaging/ffmpeg/out/<profilo>/` con `ffmpeg` o `ffmpeg.exe`,
`COPYING.LGPLv2.1` e `SOURCE.txt`. Il pacchetto PyInstaller copia
l'eseguibile in `ffmpeg/` dentro il bundle (`sys._MEIPASS/ffmpeg/ffmpeg[.exe]`),
dove lo cerca `engine/ffmpeg.locate()`. Variabili utili: `FFMPEG_JOBS`,
`FFMPEG_WORK_DIR` (senza spazi: configure non li accetta).
Chiave di cache consigliata: hash di `VERSION`, `SOURCE_SHA256`, `build.sh`.

| Profilo | Runner | Comando | Controlli inclusi |
|---|---|---|---|
| `legacy-intel` | macOS (Intel; su arm64 cross-compila) | `bash packaging/ffmpeg/build.sh legacy-intel` | `-arch x86_64`, `MACOSX_DEPLOYMENT_TARGET=10.15`, `lipo -archs` = solo x86_64, `otool -L` solo librerie di sistema, `packaging/macos/check_min_os.py` (serve `python3`) |
| `mac-arm64` | macOS arm64 | `bash packaging/ffmpeg/build.sh mac-arm64` | come sopra con `-arch arm64`, 11.0 |
| `linux-x64` | job con `container: quay.io/pypa/manylinux_2_28_x86_64` (fuori dal container lo script ci rientra con docker) | `bash packaging/ffmpeg/build.sh linux-x64` | `NEEDED` solo glibc, nessun simbolo `GLIBC_` oltre 2.28 |
| `win-x64` | build su **Ubuntu**, collaudo sul runner **Windows** | Ubuntu: `sudo apt-get install -y gcc-mingw-w64-x86-64-win32` e `bash packaging/ffmpeg/build.sh win-x64`, artefatto `out/win-x64/`; Windows (Git Bash): `bash packaging/ffmpeg/check_license.sh packaging/ffmpeg/out/win-x64/ffmpeg.exe`, poi i test con `STEMFORGE_FFMPEG` | `-static` + thread win32: nessuna DLL MinGW (`objdump -p`); licenza statica su Ubuntu, a runtime su Windows |

### Perché win-x64 si cross-compila da Linux

- Stesso script, stessa toolchain da `apt`, versione fissata dalla
  distribuzione del runner: niente installazione di MSYS2 sul runner
  Windows (lenta, con un gestore di pacchetti in più da fissare).
- `configure` di FFmpeg sotto MSYS2 impiega diversi minuti per i soli
  fork dei controlli; su Linux è molto più rapido.
- Con thread win32 e `-static` l'eseguibile dipende solo da DLL di
  sistema (`KERNEL32`, `msvcrt`, `bcrypt`...), verificato da `build.sh`.
- Il collaudo a runtime resta sul Windows vero: il job Windows esegue
  `check_license.sh` e i test `tests/*/test_ffmpeg_*.py`.

## Sviluppo

- Il codice cerca, in ordine: bundle congelato, `STEMFORGE_FFMPEG`
  (file o cartella), `packaging/ffmpeg/out/<profilo corrente>/`. **Mai il
  PATH**: un ffmpeg GPL dell'utente non deve entrare in gioco.
- Dev-box Windows con WSL2 (Ubuntu), senza root:

  ```bash
  eval "$(bash packaging/ffmpeg/mingw_userland.sh ~/.cache/stemforge-dev/mingw)"
  FFMPEG_WORK_DIR=/tmp/stemforge-ffmpeg-build bash packaging/ffmpeg/build.sh win-x64
  ```

- Una build `linux-x64` fuori da manylinux richiede
  `STEMFORGE_FFMPEG_ALLOW_HOST_GLIBC=1` ed è solo per sviluppo: il binario
  chiede la glibc dell'host.

## THIRD_PARTY_NOTICES

Voce da riportare: *FFmpeg <VERSION> — GNU Lesser General Public License
2.1 or later — sorgente: https://ffmpeg.org/releases/ffmpeg-<VERSION>.tar.xz
(SHA-256 in `packaging/ffmpeg/SOURCE_SHA256`) — configurazione: output di
`ffmpeg -version`, riportata anche da `engine.ffmpeg.license_info()`.*
Il testo della licenza è in `out/<profilo>/COPYING.LGPLv2.1`.
