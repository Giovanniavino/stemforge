# Collaudo manuale — consegna alle DAW

BUILD_SPEC §7.2.1: nessuna DAW si collauda in CI. Questo foglio si spunta
a mano, **dieci minuti per DAW e sistema**. Il perché di ogni controllo è
in [`README.md`](README.md).

Si copia il foglio in un issue o in un file di note, si annota in testa
macchina, sistema e versione di StemForge, e per ogni riga si scrive
`OK`, `KO` o `n/d` più una nota quando l'esito non è quello atteso.

## Preparazione (una volta, 5 minuti)

1. Scegli un brano tuo di 30–60 s con un attacco netto nei primi secondi
   (cassa, colpo di piatto): serve a vedere l'allineamento a occhio.
2. **Rinominalo** `Prova è 日本 #1 [mix].wav` prima di separarlo: la
   cartella di output avrà spazi, accenti, ideogrammi, `#` e `[ ]`, cioè i
   casi che rompono un URL fatto male.
3. Separalo con StemForge chiedendo voce, batteria, basso, altro: la
   schermata risultato mostra `vocals`, `drums`, `bass`, `other`.
4. Annota la durata di uno stem com'è mostrata in StemForge.
5. Solo Windows, facoltativo (percorso lungo): sposta il brano in una
   cartella annidata in modo che il percorso dello stem superi 260
   caratteri e ripeti il solo controllo C5 su una DAW qualsiasi.

Nella DAW: progetto **nuovo e vuoto**, alla stessa frequenza di
campionamento degli stem (di solito 44,1 kHz; se la DAW chiede di
convertire non è un difetto del drag, annotalo). La DAW **non** va avviata
come amministratore (Windows: con privilegi elevati il drag è bloccato,
anche da Esplora file).

## I controlli (uguali per ogni riga)

| # | Gesto | Esito atteso |
|---|---|---|
| C1 | DAW in primo piano, StemForge visibile dietro. **Un solo clic-e-trascina** su `vocals` nella schermata risultato, senza clic preliminare per dare il fuoco, e rilascio nella zona tracce vuota della DAW. | Il drag parte al primo tentativo (§8.4); sopra la DAW il cursore è "copia/accetta", mai "divieto". Nasce una traccia con il clip `vocals`. |
| C2 | Annulla (Ctrl/Cmd+Z). Seleziona i quattro stem in StemForge (Maiusc-clic) e trascinali **insieme**, rilascio all'inizio della timeline (battuta 1 / tempo 0) nella zona vuota. Se la DAW apre un dialogo, scegli l'opzione "tracce separate" indicata nella riga. | **Quattro tracce, una per file**, nell'ordine dei file. Se serve un modificatore o un dialogo, annotalo: è l'informazione da riportare nell'aiuto in linea. |
| C3 | Guarda i nomi. | Ogni traccia (o, dove la DAW non rinomina le tracce, ogni clip) si chiama come il file senza estensione: `vocals`, `drums`, `bass`, `other`. |
| C4 | Zoom sull'inizio, poi play di tutte e quattro insieme. | Tutti i clip iniziano allo stesso istante (0 / battuta 1), l'attacco iniziale è sulla stessa verticale in tutte le tracce, e insieme suonano come il brano originale (niente flanger o eco = niente sfasamenti). La durata coincide con quella annotata. Se la DAW ha stirato i file (warp/stretch automatico), annota l'impostazione e ripeti con lo stretch spento. |
| C5 | In StemForge premi "Mostra nel Finder / in Esplora file / nella cartella". | I quattro WAV sono **ancora nella cartella di output** (il drag è Copy, §7.2). Se la DAW ha copiato i file nel progetto è normale: l'originale deve comunque esserci. |
| C6 | Trascina un solo stem tenendo premuto il modificatore "copia" del sistema (Windows/Linux: Ctrl; macOS: Opzione) e, su macOS, anche con Cmd. | Il drop è accettato come in C1 (Qt offre solo Copy; su macOS ignora i modificatori nel filtrare le operazioni, vedi README). |

Tempo indicativo: C1 1 min, C2 2 min, C3 30 s, C4 3 min, C5 30 s, C6 1 min.

## Righe DAW × sistema

Per ogni riga: versione della DAW, esito C1…C6, note.

### Ableton Live — macOS, Windows

Gesto: Arrangement View, rilascio nello spazio vuoto **sotto** le tracce
(il manuale: un drop lì "crea una nuova traccia"). Per C2 prova **prima
senza modificatori** e annota cosa succede, poi ripeti tenendo premuto
**Cmd (Mac) / Ctrl (Win) al rilascio**: secondo il forum Ableton il
modificatore mette un file per traccia, senza i file possono finire uno
dopo l'altro sulla stessa traccia. Ripeti C2 una volta in Session View
(spazio a destra delle tracce).
Per C4: Preferenze > Record/Warp/Launch > "Auto-Warp Long Samples"
annotato; con il warp attivo i clip possono stirarsi e disallinearsi.

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

È anche il criterio di uscita di M3: quattro tracce, file integri,
allineati, gesto riuscito al primo tentativo con StemForge senza fuoco.

### Logic Pro — macOS

Gesto: area Tracce, rilascio sotto l'ultima traccia alla battuta 1. Con più
file Logic apre il dialogo "Add Selected Files to Tracks": scegli
"Create new tracks". Se chiede di convertire la frequenza o di copiare i
file nel progetto, annota la scelta (la copia non sposta l'originale, C5).

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

### FL Studio — macOS, Windows

Gesto: rilascio sulla **Playlist** all'inizio della prima traccia
(l'edizione Fruity non accetta audio sulla Playlist: lì usa il Channel
rack e annota). FL crea un canale Audio Clip per file: per C3 vale il nome
del clip/canale, non quello della traccia della Playlist. Per C2 annota se
i clip finiscono su tracce Playlist consecutive o sovrapposti.
Windows: se il cursore è "divieto" verifica per prima cosa che FL non giri
come amministratore (Image-Line KB 571).

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

### REAPER — macOS, Windows, Linux

Gesto: rilascio nella zona vuota sotto le tracce con il cursore di
modifica a 0. Con più file REAPER chiede come inserirli: scegli "separate
tracks" (la scelta si può memorizzare in Preferences > Media). Gli item
partono dal punto di rilascio: per C4 rilascia a 0 o allinea con Home.
Per C3 conta il nome dell'item/take; il nome della traccia dipende dalle
preferenze, annotalo.
Linux: annota il server grafico (X11 o Wayland) e se REAPER gira
nativo; REAPER legge `text/uri-list` (vedi README).

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Linux (X11 / Wayland: ……) — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

### Cubase — macOS, Windows

Gesto: finestra Progetto, rilascio nella zona vuota sotto le tracce alla
battuta 1. Con più file compare "Import Options": scegli "Different
Tracks". In 15.0.20 il dialogo risulta sparito (forum Steinberg): se non
appare annota dove finiscono i file. "Copy files to working directory"
copia, non sposta (C5).

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

### Studio One / Fender Studio Pro — macOS, Windows

Gesto: pagina Song, rilascio nella zona vuota dell'Arrange sotto le
tracce, all'inizio. Il comportamento con più file non è documentato:
per C2 annota se nasce una traccia per file o se serve un modificatore.

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

### Bitwig Studio — macOS, Windows, Linux

Gesto: Arranger, rilascio nella zona vuota sotto le tracce all'inizio
(prova anche il Clip Launcher per C1). Bitwig può stirare l'audio al tempo
del progetto: per C4 annota la modalità di stretch e, dalla 5.2, il
modificatore usato per importare "raw". Il comportamento con più file non
è documentato: annotalo in C2.
Linux: se Bitwig è installato da Flathub e il drop non apre nulla,
verifica che il sandbox veda la cartella di output (`~/Music/StemForge`).

- [ ] macOS — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Windows — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……
- [ ] Linux (X11 / Wayland: ……) — versione …… C1 … C2 … C3 … C4 … C5 … C6 … note ……

## Se una riga fallisce

Prima di toccare il codice, ripeti lo stesso gesto trascinando gli stessi
file **da Esplora file / Finder / file manager**:

- se fallisce anche da lì, il problema è della DAW o della sua
  configurazione (privilegi, sandbox, preferenze): si documenta qui;
- se da lì funziona e da StemForge no, è un difetto nostro: apri un issue
  con DAW, versione, sistema, gesto e, su Windows, l'elenco dei formati
  che la DAW chiede (es. con un ispettore di IDataObject). Solo allora si
  aggiunge un formato in `ui/drag_export.py`, con il test che lo dimostra.
