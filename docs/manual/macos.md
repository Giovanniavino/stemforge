# Collaudo manuale macOS

Questa checklist copre ciò che la CI non può provare (BUILD_SPEC §9.6, D6).
Nessun runner ha macOS 10.15, e nessuno ha una GPU Apple. Ci sono due
macchine:

- **A. Mac mini 2012**, macOS 10.15 Catalina, Intel. Si provano sia il
  DMG `macos-x86_64` sia lo zip `StemForge-Installer.zip`, e i due
  devono comportarsi allo stesso modo.
- **B. Un Mac Apple Silicon** (M1 o successivo, macOS 11 o successivo).
  Si prova il DMG `macos-arm64`.

Ogni riga si spunta solo se l'esito è **esattamente** quello atteso. Se
qualcosa va diversamente, annota la riga, il messaggio esatto e
`~/Library/Logs/StemForge/stemforge.log`, poi apri una issue con lo zip di
"Esporta diagnostica" (§9.9).

**Tempi.** Le verifiche richiedono circa 10 minuti per macchina. Non
sono comprese le attese lunghe, che vanno avviate per prime: il download
dei modelli (~1 GB) al primo avvio e, per lo zip, l'installazione sul Mac
mini (decine di minuti).

## 0. Prima di cominciare (su entrambe le macchine)

L'audio di prova si genera sul Mac con strumenti di sistema, quindi
niente materiale protetto. Apri il Terminale:

```sh
mkdir -p ~/StemForgeProva && cd ~/StemForgeProva
say -o prova.aiff "Uno due tre prova. Questa e' una frase di collaudo per StemForge, ripetuta. Uno due tre prova."
afconvert -f m4af -d aac  prova.aiff prova.m4a     # AAC: serve FFmpeg (D9)
afconvert -f m4af -d alac prova.aiff prova-alac.m4a
afconvert -f WAVE -d LEI16@44100 prova.aiff prova.wav
```

- [ ] I quattro file esistono (`ls -l ~/StemForgeProva`).
- [ ] Lo SHA-256 del DMG o dello zip scaricato coincide con
      `SHA256SUMS.txt` della release: `shasum -a 256 <file>`.
- [ ] Per ripartire da zero, se StemForge c'era già, togli app, dati e
      log: `rm -rf /Applications/StemForge.app ~/Library/Application\ Support/StemForge ~/Library/Logs/StemForge`.
      Lo zip in più usa `~/Library/Application Support/StemForge/build-env`,
      che il comando toglie insieme ai dati.

## A. Mac mini 2012 — macOS 10.15, Intel

### A1. DMG Intel (`StemForge-<versione>-macos-x86_64.dmg`)

- [ ] Doppio click sul DMG: si monta un volume "StemForge" con
      `StemForge.app` e un collegamento ad `Applications`.
- [ ] Trascina l'app su `Applications` ed espelli il volume.
- [ ] Contenuto del pacchetto (sezione D, colonna Intel): tutte le
      righe danno l'esito atteso.
- [ ] Primo avvio senza Developer ID: click destro su StemForge in
      Applicazioni → Apri → Apri. L'app si apre. Non deve comparire
      "è danneggiata" né "non può essere aperta su questo Mac" (quel
      messaggio vorrebbe dire un minimo di sistema sbagliato, §9.1).
- [ ] Il primo avvio mostra la barra di download dei modelli, mai una
      finestra vuota (§9.4). Poi compare la riga "Misuro la velocità di
      questo computer…", infine la finestra principale.
- [ ] Nel Terminale:
      `/Applications/StemForge.app/Contents/MacOS/StemForge --selftest --offline`
      termina con `COLLAUDO RIUSCITO`. La riga "decodifica dei formati"
      è `ok`, m4a e alac compresi.
- [ ] Nessun file `device.json` in `~/Library/Application Support/StemForge/`
      oppure, se c'è, contiene `"mps_ok": false`: il Mac Intel resta su
      CPU (D8).

Poi esegui la **sezione C** con questa installazione.

### A2. Zip (`StemForge-Installer.zip`, §9.5)

Riparti da zero (ultima riga della sezione 0), poi:

- [ ] Doppio click sullo zip: compaiono `Installa StemForge.command`,
      `Aggiorna StemForge.command`, `LEGGIMI.txt` e la cartella `StemForge`.
- [ ] `ls -l` nella cartella estratta: i due `.command` sono `-rwxr-xr-x`.
- [ ] Click destro su `Installa StemForge.command` → Apri → Apri: il
      Terminale parte. Se manca Python 3.11, lo scarica e chiede la
      password. Lo installa solo se `pkgutil --check-signature` riconosce
      la firma della Python Software Foundation.
- [ ] L'installazione non mostra mai `Building wheel for torch`,
      `numpy` o `PySide6`: si compilano solo i pacchetti Python puri
      `demucs`, `dora-search` e `antlr4-python3-runtime`.
- [ ] Alla fine compare "Fatto! StemForge e' in /Applications." e, a
      seconda dello zip, una di queste due cose:
  - [ ] zip **con** FFmpeg: nessun riquadro giallo, e prima della
        costruzione la riga "FFmpeg LGPL incluso: m4a/aac/alac saranno
        supportati.";
  - [ ] zip **senza** FFmpeg: riquadro giallo "!!! ATTENZIONE !!!" che
        dice che m4a, aac e alac non si apriranno. Mai silenzio.
- [ ] Sezione D, colonna Intel: stessi esiti del DMG. Unica differenza
      ammessa: senza FFmpeg nello zip, la riga D3 dice
      `No such file or directory`.
- [ ] PyAV non c'è nell'ambiente di build (D9):
      `~/Library/Application\ Support/StemForge/build-env/bin/python -m pip show av`
      risponde `WARNING: Package(s) not found: av`.
- [ ] Il selftest di A1 dà lo stesso risultato. Con lo zip senza FFmpeg
      l'unica riga non `ok` ammessa è "decodifica dei formati", che deve
      nominare m4a/alac. Il collaudo finisce con il suo verdetto, mai
      con un traceback.
- [ ] Rilancia `Aggiorna StemForge.command` subito dopo: non riscarica
      Python, dice "Allineo le dipendenze…" e trova tutto già installato
      (nessun download da ~1 GB), ricostruisce l'app e finisce con
      "Aggiornamento completato.". Modelli e `calibration.json` sono
      ancora al loro posto (non riparte il download al lancio successivo).

Poi esegui la **sezione C** con questa installazione.

**DMG e zip a confronto.** Spunta solo se, nelle sezioni C fatte con A1 e
con A2, gli esiti coincidono riga per riga. La sola differenza ammessa è
quella di m4a/aac/alac, se lo zip non contiene FFmpeg.

- [ ] Stesso comportamento.

## B. Mac Apple Silicon — macOS 11 o successivo

### B1. DMG arm64 (`StemForge-<versione>-macos-arm64.dmg`)

- [ ] Monta il DMG e trascina l'app su `Applications`.
- [ ] Contenuto del pacchetto (sezione D, colonna arm64): tutte le
      righe danno l'esito atteso.
- [ ] Primo avvio senza Developer ID:
  - macOS 11–14: click destro → Apri → Apri;
  - macOS 15 e successivi: il primo doppio click viene bloccato. Vai in
    Impostazioni di Sistema → Privacy e sicurezza → "Apri comunque",
    conferma con la password.
  L'app si apre e mostra download dei modelli e calibrazione come in A1.
- [ ] Monitoraggio Attività, colonna "Tipo": StemForge è `Apple`, non
      `Intel`. Se dice `Intel` è stato installato il DMG sbagliato,
      oppure la build non è arm64.
- [ ] `--selftest --offline` come in A1: `COLLAUDO RIUSCITO`.

### B2. Verifica dell'acceleratore (D8)

- [ ] Fai una prima separazione (sezione C, riga C1) con il dispositivo
      `auto`, che è il default.
- [ ] `cat ~/Library/Application\ Support/StemForge/device.json` mostra
      `"mps_ok": true` e un `"detail"` come
      `scarto MPS/CPU -NN.N dB (soglia -40.0 dB)`, con -NN.N **minore**
      di -40.
- [ ] Se invece c'è `"mps_ok": false`, la separazione deve essere
      comunque riuscita su CPU, con un avviso. Annota il `detail`: il
      verdetto negativo non è un difetto dell'app, ma la riga sopra
      resta non spuntata.
- [ ] Durante una seconda separazione, in Monitoraggio Attività →
      Finestra → Cronologia GPU, la GPU lavora. La verifica non si
      ripete: `ls -l` mostra che `device.json` ha la stessa data di prima.

Poi esegui la **sezione C** con questa installazione.

### B3. Facoltativo: lo zip via Rosetta (solo se avanza tempo)

Non è il percorso consigliato su Apple Silicon, ma lo zip promette di
funzionare anche qui (LEGGIMI). Fallo per ultimo: sostituisce l'app
arm64 in `/Applications`; alla fine rimetti quella del DMG.

- [ ] Doppio click su `Installa StemForge.command`: compare "Mac Apple
      Silicon: proseguo tramite Rosetta 2" e lo script **continua**. Un
      errore `unbound variable` subito dopo quella riga è un difetto.
- [ ] Dopo l'installazione, Monitoraggio Attività dice `Intel` per
      StemForge (è la build legacy-intel), e il selftest riesce.

## C. Separazione e consegna alla DAW (su ogni installazione)

- [ ] **C1.** Trascina `~/StemForgeProva/prova.wav` sulla finestra e
      premi "Solo voce", che imposta da solo il preset "Bilanciata"
      (§8.2). La stima del tempo compare prima di partire. Premi Separa:
      l'avanzamento si muove e finisce senza errori.
- [ ] **C2.** La cartella `~/Music/StemForge/prova/` contiene gli stem
      richiesti e `manifest.json`. I nomi sono minuscoli, senza il nome
      del brano (§7.3).
- [ ] **C3.** "Mostra nel Finder" apre quella cartella con lo stem
      selezionato evidenziato.
- [ ] **C4.** Ripeti con `prova.m4a` e `prova-alac.m4a`. Con FFmpeg nel
      pacchetto, entrambe le separazioni riescono. La prima finisce in
      `prova (2)`, perché lo stesso nome non si sovrascrive mai; la
      seconda in `prova-alac`. Senza FFmpeg (solo con lo zip che lo ha
      dichiarato a fine installazione) compare un messaggio chiaro di
      formato non supportato, mai un crash.
- [ ] **C5.** Finder: click destro su `prova.aiff` → Apri con →
      StemForge. L'app riceve il file (§9.1).
- [ ] **C6. Ableton Live** (se installato; sul Mac mini serve una
      versione per 10.15, come Live 11). Apri un set vuoto e trascina
      gli stem dalla schermata Risultato dentro l'area delle tracce:
  - [ ] nasce una traccia audio per file, con il nome dello stem
        (`vocals`…);
  - [ ] tutte le clip iniziano a 1.1.1 e hanno la stessa durata del
        brano: allineate al campione;
  - [ ] in riproduzione, la traccia `vocals` fa sentire la frase di
        prova.
- [ ] **C7.** Chiudi e riapri l'app: niente download, niente
      calibrazione, subito la finestra principale (offline per sempre,
      §9.2). Prova anche col Wi-Fi spento.

## D. Contenuto del pacchetto (un minuto, dal Terminale)

Comandi di sola lettura sull'app installata. `A=/Applications/StemForge.app`
va incollato una volta prima delle righe.

| Riga | Comando | Intel (A1, A2) | arm64 (B1) |
|---|---|---|---|
| D1 | `defaults read "$A/Contents/Info" LSMinimumSystemVersion` | `10.15` | `11.0` |
| D2 | `file "$A/Contents/MacOS/StemForge"` | `x86_64` | `arm64` |
| D3 | `file "$A/Contents/Frameworks/ffmpeg/ffmpeg"` | `Mach-O 64-bit executable x86_64` | `Mach-O 64-bit executable arm64` |
| D4 | `ls "$A/Contents/Frameworks" \| grep -iE '^av($\|\.)'` | nessuna riga: PyAV (GPLv3) assente, D9 | idem |
| D5 | `ls "$A/Contents/Resources/i18n"` | i file `.qm` delle traduzioni, se la versione ne ha | idem |
| D6 | `codesign --verify --strict "$A" && echo firma-ok` | `firma-ok` (anche ad-hoc) | idem |

- [ ] D1–D6 danno l'esito della colonna della macchina.

## Esito

| Macchina | Installazione | Data | Versione | Sistema | Tutto spuntato? | Note |
|---|---|---|---|---|---|---|
| Mac mini 2012 | DMG x86_64 | | | 10.15.7 | | |
| Mac mini 2012 | zip | | | 10.15.7 | | |
| Apple Silicon | DMG arm64 | | | | | |
