**StemForge** splits a song into its tracks and lets you drag them straight
into the project you already have open in your DAW. Everything runs on your
computer: no account, no cloud, no telemetry.
*[Italiano più sotto](#in-italiano).*

## Which file to download

| Your computer | File |
|---|---|
| Mac with Apple chip (M1, M2, M3, M4…), macOS 11 Big Sur or later | `StemForge-…-macos-arm64.dmg` |
| Mac with Intel processor, macOS 10.15 Catalina or later | `StemForge-…-macos-x86_64.dmg` |
| PC with Windows 10 (1809 or later) or Windows 11, 64-bit | `StemForge-…-windows-x64-setup.exe` |
| PC with Linux x64, glibc 2.28 or later (Ubuntu 20.04, Debian 11, Fedora 29 and later) | `StemForge-…-linux-x86_64.AppImage` |

Not sure which Mac you have? Apple menu (the apple, top left) → **About This Mac**: "Chip Apple
M…" is Apple Silicon, "Processor Intel…" is Intel. The Intel file also runs
on Apple Silicon through Rosetta, but slower and without the GPU: take the
`arm64` one. Windows on ARM uses the x64 file through emulation.

Only the Apple Silicon GPU is used, and only after it has proven to give
the same result as the CPU; everything else runs on the CPU. Linux is a
second-tier platform: built and tested automatically, tried by hand less
often.

## Install

- **Mac:** open the `.dmg` and drag StemForge into Applications.
- **Windows:** run the `setup.exe`. No administrator rights needed.
- **Linux:** `chmod +x StemForge-*.AppImage`, then run it. If it complains
  about FUSE, see [the guide](https://github.com/Giovanniavino/stemforge#linux--the-appimage-doesnt-start).
- **Mac mini and other old Intel Macs:** `StemForge-Installer.zip`, which
  builds the app on your Mac, is still available as an alternative to the
  Intel DMG ([how](https://github.com/Giovanniavino/stemforge#install)).

On first launch StemForge downloads the separation models (about 1 GB, once,
from `dl.fbaipublicfiles.com`), checks the GPU on Apple Silicon and measures
this computer's speed, so that every time estimate is calibrated on *your*
machine. After that it works offline.

## If the system says the developer can't be verified

This release is not signed with a paid Apple or Microsoft certificate yet:
the warning is expected. First check that the file is the one published
here, against `SHA256SUMS.txt`
([how](https://github.com/Giovanniavino/stemforge#check-the-sha-256)).

- **macOS 15 Sequoia and later:** try to open the app, close the warning, then
  System Settings → Privacy & Security → at the bottom **Open Anyway**.
- **macOS 10.15 to 14:** Control-click StemForge → **Open** → **Open**.
- **Windows:** on the blue SmartScreen screen → **More info** → **Run anyway**.

Only the first time. Step-by-step guide: [The app won't open](https://github.com/Giovanniavino/stemforge#the-app-wont-open).

## How this release was tested

Before publication every package was installed and tested automatically on
its own platform with the built-in self-test (`StemForge --selftest`): a
real separation in the worker process, sample-exact stem length and sample
rate, decoding of WAV, FLAC, OGG, MP3, M4A and ALAC, the interface, the
HTTPS certificates. For the Macs, every binary is also checked to declare a
minimum macOS no higher than the one promised.

Not covered by automatic tests, checked by hand:

- the Intel DMG on a real macOS 10.15 machine and the Apple GPU on a real
  Apple Silicon Mac (no CI runner has either);
- drag & drop into each DAW: <!-- fill in for this release: DAW / system combinations checked by hand (docs/daw/) -->

Every component bundled in the packages and its license:
[THIRD_PARTY_NOTICES](https://github.com/Giovanniavino/stemforge/blob/main/THIRD_PARTY_NOTICES).

---

## In italiano

**StemForge** separa un brano nelle sue tracce e te le fa trascinare
direttamente nel progetto già aperto nella DAW. Tutto gira sul tuo
computer: niente account, niente cloud, niente telemetria.

### Quale file scaricare

| Il tuo computer | File |
|---|---|
| Mac con chip Apple (M1, M2, M3, M4…), macOS 11 Big Sur o successivo | `StemForge-…-macos-arm64.dmg` |
| Mac con processore Intel, macOS 10.15 Catalina o successivo | `StemForge-…-macos-x86_64.dmg` |
| PC con Windows 10 (1809 o successiva) o Windows 11, 64 bit | `StemForge-…-windows-x64-setup.exe` |
| PC con Linux x64, glibc 2.28 o successiva (Ubuntu 20.04, Debian 11, Fedora 29 e successive) | `StemForge-…-linux-x86_64.AppImage` |

Non sai che Mac hai? Menu Apple (la mela in alto a sinistra) → **Informazioni su questo Mac**: "Chip Apple
M…" è Apple Silicon, "Processore Intel…" è Intel. Il file Intel gira anche
sui Mac Apple Silicon tramite Rosetta, ma più lento e senza GPU: prendi
quello `arm64`.

### Installazione

- **Mac:** apri il `.dmg` e trascina StemForge in Applicazioni.
- **Windows:** esegui il `setup.exe`. Non servono diritti di amministratore.
- **Linux:** `chmod +x StemForge-*.AppImage`, poi avvialo.
- **Mac mini e Mac Intel vecchi:** resta disponibile anche
  `StemForge-Installer.zip`, che costruisce l'app sul tuo Mac
  ([come](https://github.com/Giovanniavino/stemforge/blob/main/docs/it/installazione.md#mac-mini-e-mac-intel-vecchi-linstaller-zip)).

Al primo avvio l'app scarica i modelli di separazione (~1 GB, una volta
sola), controlla la GPU sui Mac Apple Silicon e misura la velocità del
computer per stimare i tempi in modo onesto. Da lì in poi funziona offline.

### Se il sistema avvisa che lo sviluppatore non è verificato

Questa versione non è ancora firmata con un certificato Apple/Microsoft a
pagamento: l'avviso è atteso. Prima controlla che il file sia quello
pubblicato qui, con `SHA256SUMS.txt`.

- **macOS 15 Sequoia e successivi:** prova ad aprire l'app, chiudi
  l'avviso, poi Impostazioni di Sistema → Privacy e sicurezza → in fondo
  **Apri comunque**.
- **macOS da 10.15 a 14:** click destro su StemForge → **Apri** → **Apri**.
- **Windows:** nella finestra blu di SmartScreen → **Ulteriori
  informazioni** → **Esegui comunque**.

Serve solo la prima volta. Guida passo passo:
[Se l'app non si apre](https://github.com/Giovanniavino/stemforge/blob/main/docs/it/installazione.md#se-lapp-non-si-apre).
