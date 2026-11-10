# Linux (AppImage x64) — checklist manuale

Profilo `linux-x64`, seconda fascia (BUILD_SPEC §2.1, §9.8): AppImage x64,
solo CPU, costruita in `manylinux_2_28` (glibc 2.28). La CI costruisce
l'AppImage e la collauda con `--selftest` in container Ubuntu 20.04 e
24.04 **senza schermo**: tutto ciò che richiede una sessione grafica vera,
una GPU, un server audio o una DAW sta qui, e si spunta a mano.

Per ogni riga: sistema (distribuzione, versione, X11 o Wayland), data,
chi l'ha provata, esito. Una riga non provata resta vuota: non si
deduce da un'altra distribuzione.

## 0. Cosa serve sulla macchina

L'AppImage porta con sé Python, torch, Qt, le librerie X11 che Qt 6.7
chiede e che una distribuzione desktop non installa sempre
(`libxcb-cursor0`, `xcb-util-*`, `libxkbcommon-x11`), libsndfile e il
FFmpeg LGPL. Lascia al sistema solo ciò che **deve** essere del sistema
(elenco e motivi in `packaging/linux/host_libs.txt`): glibc ≥ 2.28,
libstdc++, OpenGL/EGL (driver della GPU), libX11/libxcb, fontconfig e
freetype, le librerie client di Wayland, D-Bus, GLib, PulseAudio/ALSA.
Ogni desktop Linux le ha già.

Per montare l'AppImage serve `fusermount` o `fusermount3` (pacchetto
`fuse` o `fuse3`: presente di default su Ubuntu 20.04 e 24.04, Fedora,
Debian con desktop). **Non** serve `libfuse2`: il runtime è il type2
statico. Senza FUSE: `--appimage-extract-and-run` (vedi §2).

## 1. Installazione

| # | Gesto | Esito atteso | Sistema / data / esito |
|---|---|---|---|
| 1.1 | Scaricare `StemForge-X.Y.Z-linux-x86_64.AppImage` e `SHA256SUMS.txt` dalla release; `sha256sum -c --ignore-missing SHA256SUMS.txt` | `StemForge-X.Y.Z-linux-x86_64.AppImage: OK` | |
| 1.2 | `chmod +x StemForge-*.AppImage` (o Proprietà → "Consenti l'esecuzione come programma") | il file diventa eseguibile | |
| 1.3 | Facoltativo, integrazione nel menu: `./StemForge-*.AppImage --appimage-extract 'usr/share/applications/*'` e `'usr/share/icons/*'`, poi copiare il `.desktop` in `~/.local/share/applications/` correggendo `Exec=` col percorso assoluto dell'AppImage | StemForge compare nel menu applicazioni con la sua icona | |
| 1.4 | Con un gestore AppImage (Gear Lever, AppImageLauncher), se l'utente ne ha uno | integrazione senza errori, nessuna richiesta di aggiornamento automatico (l'AppImage non ne dichiara: niente auto-update, §0) | |

## 2. Avvio

| # | Gesto | Esito atteso | Sistema / data / esito |
|---|---|---|---|
| 2.1 | Doppio clic dal file manager, sessione **X11** | finestra principale; primo avvio: download dei pesi con avanzamento, poi calibrazione con la riga di spiegazione (§9.4); mai una finestra vuota | |
| 2.2 | Stesso, sessione **Wayland** (GNOME o KDE Plasma) | come 2.1. Verificare da terminale che giri nativo su Wayland: `QT_DEBUG_PLUGINS=1 ./StemForge-*.AppImage 2>&1 \| grep -i wayland` mostra il plugin `wayland` caricato | |
| 2.3 | Sessione Wayland, forzando X11: `QT_QPA_PLATFORM=xcb ./StemForge-*.AppImage` | parte via XWayland (è il ripiego se il drag su Wayland desse problemi, §4) | |
| 2.4 | Da terminale: `./StemForge-*.AppImage --selftest --report ~/stemforge-selftest.json` | `COLLAUDO RIUSCITO`, uscita 0; il report elenca ogni controllo con `ok` | |
| 2.5 | Senza FUSE (per esempio dentro un container o una VM minimale): `./StemForge-*.AppImage --appimage-extract-and-run` | parte lo stesso | |
| 2.6 | "Apri con" dal file manager su un `.wav`/`.flac`/`.mp3`/`.m4a`, dopo l'integrazione di 1.3 | StemForge si apre col brano già caricato | |
| 2.7 | Schermo HiDPI con scala 200% (GNOME) e 150% (KDE) | testo e icone nitidi, niente finestra minuscola | |
| 2.8 | Anteprima di uno stem nella schermata risultato (PipeWire su 24.04, PulseAudio su 20.04) | si sente; nessun errore di QtMultimedia nel log | |

## 3. Separazione

| # | Gesto | Esito atteso | Sistema / data / esito |
|---|---|---|---|
| 3.1 | Trascinare nella finestra un brano vero di 3–4 minuti, chiedere voce + batteria + basso + altro, qualità standard | gli stem compaiono in `~/Music/StemForge/<brano>/` (o nella cartella Musica localizzata da `xdg-user-dir MUSIC`), con `manifest.json` | |
| 3.2 | Stesso brano in `.m4a` (AAC) e in ALAC | letti dal FFmpeg LGPL del pacchetto, nessun errore di formato | |
| 3.3 | Durante la separazione, `top`: un solo processo worker che usa i core della CPU | nessun processo orfano dopo la fine o dopo "Annulla" | |
| 3.4 | Separare due volte lo stesso brano | seconda cartella con suffisso ` (2)`, la prima intatta (§7.3) | |

## 4. Drag verso le DAW (§7.2.1)

Il drag porta una lista di URL `file://` (`text/uri-list`), azione
**Copia**: dopo il drop gli stem devono restare nella cartella di
StemForge. Provare **sia su X11 sia su Wayland**: su Wayland StemForge è
nativo, mentre una DAW può girare via XWayland, e il drag passa dal ponte
del compositore.

Se la DAW è installata come **Flatpak**, il sandbox può impedirle di
leggere la cartella degli stem: annotare il tipo di installazione
(tarball/.deb ufficiale o Flatpak) nell'esito.

| # | DAW, gesto | Esito atteso | Sistema / data / esito |
|---|---|---|---|
| 4.1 | **Bitwig Studio** (Linux, .deb o Flatpak): trascinare **uno** stem nell'arranger | nuova traccia audio con la clip; il file resta in `~/Music/StemForge/...` | |
| 4.2 | Bitwig: selezionare **quattro** stem e trascinarli insieme | una clip/traccia per file, nell'ordine della selezione | |
| 4.3 | Bitwig: trascinare uno stem nel browser dei file o in una traccia esistente | importato nella traccia, nessuna copia rifiutata | |
| 4.4 | **Reaper** (Linux, tarball ufficiale): trascinare uno stem nell'area tracce | nuova traccia con l'item audio alla posizione del drop | |
| 4.5 | Reaper: trascinare quattro stem insieme | Reaper chiede come disporli (una traccia per file / in sequenza); con "una traccia per file" quattro tracce allineate a inizio brano | |
| 4.6 | Reaper: dopo il drop, "Media Explorer" o proprietà dell'item | il percorso è quello in `~/Music/StemForge/...` (Reaper non copia se non configurato a farlo) e il file è intero (durata uguale al brano) | |
| 4.7 | Verso il file manager (Nautilus/Dolphin) | il file viene **copiato**, non spostato | |
| 4.8 | Ripetere 4.1 e 4.4 con `QT_QPA_PLATFORM=xcb` se su Wayland il drag non arriva | annotare quale delle due piattaforme funziona: è un'informazione per la documentazione utente | |

## 5. Distribuzioni

Il minimo promesso è glibc 2.28. Le distribuzioni da provare almeno una
volta per release, in ordine di priorità:

| Distribuzione | Sessione | 2.1/2.2 | 2.4 | 3.1 | 4.x | Data / chi |
|---|---|---|---|---|---|---|
| Ubuntu 24.04 LTS | Wayland (GNOME) | | | | | |
| Ubuntu 22.04 LTS | X11 | | | | | |
| Ubuntu 20.04 LTS | X11 | | | | | |
| Fedora (ultima) | Wayland | | | | | |
| Debian 11 o 12 | X11 | | | | | |
| Linux Mint / KDE neon | X11 / Wayland (KDE) | | | | | |

## 6. Disinstallazione

| # | Gesto | Esito atteso | Sistema / data / esito |
|---|---|---|---|
| 6.1 | Cancellare il file `.AppImage` (e il `.desktop` copiato in 1.3) | StemForge sparisce dal menu | |
| 6.2 | Facoltativo: cancellare `~/.local/share/stemforge` (pesi dei modelli, calibrazione) | ~1 GB liberato; gli stem in `~/Music/StemForge` restano | |

## Diagnosi rapida

- **"could not load the Qt platform plugin xcb"**: non dovrebbe mai
  succedere (le librerie xcb sono nel pacchetto); se succede, lanciare con
  `QT_DEBUG_PLUGINS=1` e allegare l'output alla issue: la libreria
  mancante è un errore del pacchetto, non dell'utente.
- **L'AppImage non parte e parla di FUSE**: installare `fuse3` (o
  `fuse`) oppure usare `--appimage-extract-and-run`.
- **Esporta diagnostica** (schermata iniziale, §9.9) produce lo zip da
  allegare alle issue.
