# Installazione

[← Indice della guida](README.md)

## Quale file scaricare

Ogni versione pubblicata nella pagina
[Releases](https://github.com/Giovanniavino/stemforge/releases) contiene un
file per ogni tipo di computer. Scegli la riga che corrisponde al tuo:

| Il tuo computer | File da scaricare | Accelerazione |
|---|---|---|
| Mac con chip Apple (M1, M2, M3, M4…), macOS 11 Big Sur o successivo | `StemForge-<versione>-macos-arm64.dmg` | GPU Apple, dopo un controllo di correttezza |
| Mac con processore Intel, macOS 10.15 Catalina o successivo | `StemForge-<versione>-macos-x86_64.dmg` | solo CPU |
| PC con Windows 10 (versione 1809 o successiva) o Windows 11, 64 bit | `StemForge-<versione>-windows-x64-setup.exe` | solo CPU |
| PC con Linux x64 (Ubuntu 20.04, Debian 11, Fedora 29 o successive) | `StemForge-<versione>-linux-x64.AppImage` | solo CPU |

**Non sai che Mac hai?** Menu  → **Informazioni su questo Mac**: se vedi
"Chip Apple M…" è Apple Silicon, se vedi "Processore Intel…" è Intel. La
versione Intel funziona anche sui Mac Apple Silicon tramite Rosetta, ma
più lenta e senza GPU: su un Mac Apple scegli il file `arm64`.

**Windows su processore ARM** (alcuni portatili Surface e Snapdragon): usa
il file x64, che Windows esegue in emulazione.

Accanto ai file c'è `SHA256SUMS.txt`, che serve a controllare che il file
scaricato sia proprio quello pubblicato ([come si fa](#controllare-lo-sha-256)).

## Requisiti

| Profilo | Sistema minimo |
|---|---|
| Mac Intel (`legacy-intel`) | macOS 10.15 Catalina, qualunque Mac Intel che lo installi (basta un Mac mini del 2012) |
| Mac Apple Silicon (`mac-arm64`) | macOS 11 Big Sur: ogni Mac con chip Apple |
| Windows (`win-x64`) | Windows 10 versione 1809 o Windows 11, 64 bit |
| Linux (`linux-x64`) | glibc 2.28 o successiva (Ubuntu 20.04, Debian 11, Fedora 29 e successive), 64 bit |

- **Spazio su disco:** circa 1 GB per i modelli di separazione (scaricati
  una volta sola), più lo spazio per gli stem: uno stem stereo a 24 bit
  occupa circa 15 MB per minuto di audio. StemForge controlla lo spazio
  libero **prima** di cominciare, non a metà.
- **Memoria:** con 8 GB di RAM si lavora tranquilli. Con meno, chiudi le
  altre app o usa il preset **Veloce**.
- **Internet:** serve una volta sola, al primo avvio, per scaricare i
  modelli.

Linux è una piattaforma di seconda fascia: viene costruita e collaudata
automaticamente, ma provata a mano meno di macOS e Windows.

## Installare

### Mac (DMG)

1. Apri il file `.dmg` con un doppio click.
2. Trascina **StemForge** nella cartella **Applicazioni**.
3. Espelli il disco "StemForge" dalla barra laterale del Finder.

La prima volta macOS avvisa che lo sviluppatore non è verificato: vedi
[Se l'app non si apre](#se-lapp-non-si-apre).

### Mac mini e Mac Intel vecchi: l'installer zip

Per i Mac Intel c'è anche un'altra strada, quella provata per mesi sul
Mac mini del 2012: il pacchetto `StemForge-Installer.zip`, che costruisce
l'app direttamente sul tuo Mac.

1. Fai doppio click sullo zip per estrarlo. (Chi te lo manda deve mandare
   lo zip così com'è, senza estrarlo prima: una cartella già estratta e
   inviata via chat arriva rotta.)
2. Fai doppio click su **"Installa StemForge.command"**. Se macOS dice che
   arriva da uno sviluppatore non identificato: click destro sul file →
   **Apri** → **Apri**.
3. Segui il Terminale: fa tutto da solo. Se manca Python scarica quello
   ufficiale di python.org e ti chiede la password del Mac; ogni componente
   scaricato è verificato con il suo SHA-256. Durante l'installazione serve
   internet.
4. Alla fine trovi StemForge in **Applicazioni**.

Per aggiornare un'installazione fatta così usa **"Aggiorna
StemForge.command"**: non riscarica tutto e ci mette pochi minuti.

### Windows

1. Esegui `StemForge-<versione>-windows-x64-setup.exe`.
2. Se compare la finestra blu di SmartScreen vedi
   [qui sotto](#windows--smartscreen).
3. Segui l'installazione. **Non servono i diritti di amministratore**:
   l'app si installa per il tuo utente (dal dialogo iniziale puoi scegliere
   di installarla per tutti).

Trovi StemForge nel menu Start; l'icona sul desktop è facoltativa.
L'installer aggiunge StemForge alla voce **Apri con** dei file audio,
senza cambiare il programma che li apre di solito.

### Linux (AppImage)

```bash
chmod +x StemForge-<versione>-linux-x64.AppImage
./StemForge-<versione>-linux-x64.AppImage
```

Oppure: click destro sul file → Proprietà → Permessi → "Consenti
l'esecuzione come programma", poi doppio click.

## Il primo avvio

Il primo avvio fa tre cose, ognuna con la sua barra di avanzamento — mai
una finestra vuota che sembra bloccata:

1. **Scarica i modelli di separazione** (circa 1 GB, una volta sola) dal
   server ufficiale di Demucs, `dl.fbaipublicfiles.com`. Ogni file è
   controllato con uno SHA-256 fissato nel codice: un download interrotto a
   metà viene riconosciuto e rifatto. Se non c'è rete, l'app lo dice
   chiaramente: la connessione serve **una sola volta**, poi StemForge
   funziona offline per sempre.
2. **Controlla la GPU — solo sui Mac Apple Silicon.** Prima di fidarsi
   della GPU, StemForge separa lo stesso breve audio sintetico sulla GPU e
   sulla CPU e confronta i risultati. La GPU si usa solo se i due
   coincidono; altrimenti si resta sulla CPU, più lenta ma sempre esatta.
   Se durante un lavoro la GPU fallisce, quella passata si rifà sulla CPU e
   l'app ti avvisa.
3. **Calibra:** *"Misuro la velocità di questo computer per darti stime
   oneste."* Un breve test misura quanto è veloce il tuo computer a
   separare. Tutte le stime di tempo che vedrai vengono da qui, e
   migliorano con ogni brano che separi.

Poi si apre la finestra principale: vai a [Uso](uso.md).

## Se l'app non si apre

StemForge per ora non è firmato con un certificato Apple o Microsoft a
pagamento, quindi la prima volta il sistema avvisa. L'avviso è atteso;
quello che conta è che il file sia quello pubblicato:
[controlla lo SHA-256](#controllare-lo-sha-256) prima di procedere. Serve
farlo una volta sola.

### macOS da 10.15 Catalina a 14 Sonoma

1. Apri la cartella **Applicazioni** nel Finder.
2. Click destro (o Ctrl-click) su **StemForge** → **Apri**.
3. Nella finestra di avviso, click di nuovo su **Apri**.

Se il pulsante **Apri** non c'è: prova ad aprire l'app una volta, poi vai
in **Preferenze di Sistema → Sicurezza e Privacy → Generali** (su macOS 13
e 14: **Impostazioni di Sistema → Privacy e sicurezza**) e premi **Apri
comunque** accanto al messaggio su StemForge.

### macOS 15 Sequoia e successivi

Da macOS 15 il click destro → Apri non basta più.

1. Doppio click su StemForge. Quando macOS dice che non è stato aperto,
   premi **Fine**.
2. Apri **Impostazioni di Sistema → Privacy e sicurezza** e scorri fino
   alla sezione **Sicurezza**.
3. Accanto a *"StemForge" è stato bloccato…* premi **Apri comunque**,
   conferma con la password del Mac o con Touch ID, poi **Apri**.

### "StemForge è danneggiato e non può essere aperto" (macOS)

Può succedere se un programma di download altera la firma dell'app.
Controlla prima lo SHA-256. Se coincide, togli il contrassegno di
quarantena dal Terminale e poi apri l'app come sopra:

```bash
xattr -dr com.apple.quarantine /Applications/StemForge.app
```

### Windows — SmartScreen

1. Nella finestra blu *"PC protetto da Windows"*, click su **Ulteriori
   informazioni**.
2. Click su **Esegui comunque**.

Se è il browser a bloccare il download ("non viene scaricato
comunemente"), apri l'elenco dei download e scegli **Mantieni** →
**Mantieni comunque**.

### Linux — l'AppImage non parte

- Controlla che sia eseguibile: `chmod +x StemForge-*.AppImage`.
- Se l'errore parla di **FUSE**, installa il pacchetto FUSE della tua
  distribuzione, oppure avvia l'AppImage senza FUSE:
  `./StemForge-<versione>-linux-x64.AppImage --appimage-extract-and-run`.

## Controllare lo SHA-256

Scarica anche `SHA256SUMS.txt` dalla stessa pagina e confronta:

| Sistema | Comando | Con cosa confrontare |
|---|---|---|
| macOS (Terminale) | `shasum -a 256 ~/Downloads/StemForge-*.dmg` | la riga di quel file in `SHA256SUMS.txt` |
| Windows (PowerShell) | `Get-FileHash $HOME\Downloads\StemForge-*-setup.exe -Algorithm SHA256` | come sopra |
| Linux (terminale, nella cartella dei download) | `sha256sum -c SHA256SUMS.txt --ignore-missing` | deve stampare `OK` |

Se il valore è diverso **non aprire il file**: riscaricalo dalla pagina
Releases.

## Disinstallare

- **Mac:** trascina StemForge da Applicazioni al Cestino. Per recuperare
  anche il GB dei modelli, cancella `~/Library/Application Support/StemForge/`
  e `~/Library/Logs/StemForge/` (nel Finder: menu Vai → Vai alla cartella…).
- **Windows:** Impostazioni → App → StemForge → Disinstalla. Il
  disinstallatore **chiede** se cancellare anche modelli e calibrazione
  (circa 1 GB): rispondi sì se non pensi di reinstallarlo.
- **Linux:** cancella l'AppImage e le cartelle `~/.local/share/stemforge/`
  e `~/.local/state/stemforge/`.

Gli stem che hai separato restano in `~/Music/StemForge/` (Musica →
StemForge): sono tuoi, nessuna disinstallazione li tocca.
