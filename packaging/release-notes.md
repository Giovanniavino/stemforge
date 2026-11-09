## Quale file scaricare

| Il tuo computer | File |
|---|---|
| Mac con chip Apple (M1, M2, M3, M4…), macOS 11 o successivo | `StemForge-…-macos-arm64.dmg` |
| Mac con processore Intel, macOS 10.15 Catalina o successivo | `StemForge-…-macos-x86_64.dmg` |
| PC Windows 10 o 11 | `StemForge-…-windows-x64-setup.exe` |

Non sai che Mac hai? Menu  → **Informazioni su questo Mac**: se vedi "Chip Apple M…" è Apple Silicon, se vedi "Processore Intel…" è Intel.

## Installazione

**Mac** — apri il `.dmg` e trascina StemForge nella cartella Applicazioni.

**Windows** — esegui il file `setup.exe`. Non servono diritti di amministratore.

Al primo avvio l'app scarica i modelli di separazione (~1 GB, una volta sola) e misura la velocità del computer per stimare i tempi in modo onesto. Da lì in poi funziona offline.

## Se il sistema avvisa che lo sviluppatore non è verificato

Questa versione non è ancora firmata con un certificato Apple/Microsoft a pagamento: l'avviso è atteso, il file è quello pubblicato qui (controlla l'hash in `SHA256SUMS.txt`).

- **macOS 15 Sequoia e successivi**: prova ad aprire l'app, chiudi l'avviso, poi Impostazioni di Sistema → Privacy e sicurezza → in fondo **Apri comunque**.
- **macOS 14 e precedenti**: click destro su StemForge → **Apri** → **Apri**.
- **Windows**: nella finestra blu di SmartScreen → **Ulteriori informazioni** → **Esegui comunque**.

Serve solo la prima volta.

## Collaudo

Ogni file qui sotto è stato installato e collaudato automaticamente prima della pubblicazione: separazione reale di un brano, allineamento al campione degli stem, lettura di WAV/FLAC/OGG/MP3/M4A, interfaccia, certificati HTTPS. Per i Mac è verificato anche che ogni componente dichiari un macOS minimo non superiore a quello promesso.
