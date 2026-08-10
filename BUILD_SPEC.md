# StemForge — Specifica di costruzione

> Documento unico e autosufficiente. Chi implementa non deve chiedere nulla:
> ogni decisione è già presa qui, con la motivazione accanto.

Versione spec: 2.3 · Target: **macOS 10.15+ (Catalina) su Mac Intel (x86_64), solo CPU** · Data: 2026-08-10

### Changelog 2.2 → 2.3

- Target abbassato a **macOS 10.15 Catalina**: la macchina reale del
  committente è un Mac mini Late 2012, che si ferma lì. Conseguenze:
  - **Python 3.11** sul target (non 3.12: PySide6 6.4 richiede <3.12);
  - **PySide6 pinnato == 6.4.3**: è l'ultima serie basata su Qt 6.4,
    l'ultima Qt che supporta macOS < 11. Non alzare senza cambiare
    target. Sul dev-box Windows resta ammessa una PySide6 recente: il
    codice UI usa solo API presenti in entrambe;
  - torch/torchaudio 2.2.2 restano validi (wheel x86_64 dichiarano
    macOS 10.9/10.13+);
  - `LSMinimumSystemVersion = 10.15`; PyInstaller >= 6.6 supporta
    macOS 10.15+.
- Aggiunto il pacchetto di installazione inviabile (§9.5): zip con
  script doppio-click che costruisce l'app nativamente sul Mac
  dell'utente.

**Priorità dichiarata dal committente:** la qualità del risultato viene
prima del tempo di calcolo. Un'attesa di ore su un Mac vecchio è
accettabile; uno stem mediocre non lo è. Ogni compromesso qualità/velocità
in questa spec è risolto a favore della qualità.

### Changelog 2.1 → 2.2

- Target corretto: da Apple Silicon/MPS a **Intel x86_64, solo CPU**.
  Sviluppo su Windows + GPU NVIDIA (CUDA) ammesso come ambiente di lavoro,
  ma il target di consegna è il Mac Intel.
- Stack pinnato a `torch==2.2.2` (ultima versione con wheel macOS x86_64)
  e `numpy < 2` (§2).
- Tutti i tempi assoluti declassati da **vincolo** a **informazione**.
  Resta vincolante la scalabilità (O7) e l'onestà della stima (§8.2.1).
- Preset di default: **`best`**. L'insieme completo non viene mai
  sacrificato in `best` (§5.1.1, §5.6).
- IPC unificato: **QProcess + JSON-lines su stdio** (D2). Eliminato
  `multiprocessing`.
- Blocchi per file lunghi: overlap-add a finestre complementari, che
  preserva l'invariante di ricostruzione (§5.7).
- Annullamento: la garanzia del secondo la dà l'uccisione del processo,
  non `should_cancel` (§5.5).
- Aggiunta la tabella dei modelli di 2° stadio e RoFormer con fonti,
  licenze e procedura di fissaggio degli hash (§5.8).
- Packaging: `target_arch = "x86_64"`, firma senza `--deep` (§9).
- Stima dello spazio disco calcolata dal piano, non con un fattore fisso
  (§10.1).
- Calibrazione dei costi al primo avvio sulla macchina reale (§8.2.1).

---

## 0. Cos'è e cosa non è

**StemForge è un'applicazione desktop standalone che prende un file audio,
lo separa nelle tracce strumentali scelte dall'utente, e le rende
trascinabili direttamente nel progetto DAW già aperto.**

L'utente fa tre cose: trascina un brano dentro l'app, spunta gli strumenti
che vuole, preme Separa. Poi trascina gli stem dall'app dentro il suo
arrangiamento Ableton, senza aprire, importare o salvare niente.

### Obiettivi

| # | Obiettivo | Verificabile come |
|---|---|---|
| O1 | Separazione multi-strumento con scelta dell'utente | §5 |
| O2 | Drag & drop diretto nel progetto DAW aperto | §7 |
| O3 | App standalone, doppio click, zero terminale, zero Python da installare | §9 |
| O4 | Qualità: nessuna regressione udibile rispetto a Demucs `htdemucs_ft` completo | §11 |
| O5 | **Onestà sul tempo**: prima di partire l'utente vede una stima calibrata sulla *sua* macchina, e la stima non mente | §8.2.1 |
| O6 | Non blocca mai: UI reattiva e annullabile durante l'elaborazione | §8.4 |
| O7 | **Il tempo scala con quanto si chiede**: un solo stem costa una frazione di tutti | §5.3 |

Non c'è un obiettivo di tempo assoluto. Su un Mac Intel senza GPU la
separazione completa di un brano richiede decine di minuti, e va bene
così: il committente preferisce aspettare che rinunciare alla qualità.
Ciò che non va bene è *mentire* sull'attesa (O5) o far pagare l'attesa
piena a chi chiede una traccia sola (O7).

### Non-obiettivi — da rifiutare se emergono in corso d'opera

- **Non è un plugin VST/AU.** Niente processing in tempo reale. Vedi §7.0.
- **Non genera file di progetto DAW** (`.als`, `.RPP`, AAF). L'utente
  lavora nel progetto che ha già aperto: aprirne uno nuovo generato
  dall'app sarebbe una scocciatura in più, non una comodità. Il trasporto
  è il drag & drop.
- **Niente slicing, pad, sampler, sequencer, effetti, mixer.** Il progetto
  precedente è morto di questo. Se una feature non serve a separare o a
  consegnare gli stem, non entra.
- **Niente editing audio.** Nessun trim, fade, EQ. Lo fa la DAW.
- **Niente cloud, account, telemetria, auto-update.** Gira offline.
- **Niente training di modelli.** Si usano pesi pre-addestrati.

---

## 1. Decisioni architetturali

Ognuna con la ragione. Non cambiarle senza una ragione più forte.

### D1 — Il motore è in Python, non in C++ o Java

Tutti i modelli di separazione allo stato dell'arte escono in PyTorch.
Riscrivere l'inferenza in C++ non aggiunge un decibel: il tempo è speso
dentro le primitive tensoriali, che sono già C++ compilato. Il linguaggio
dell'involucro è irrilevante per la qualità e quasi irrilevante per la
velocità.

Java è escluso senza appello: nessun ecosistema ML audio, e la JVM è un
peso morto in un'app che deve muovere centinaia di MB di float.

C++ tornerà utile solo in §13.2, se un giorno si vorrà eliminare la
dipendenza da torch. Non è nello scope della v1.

### D2 — Processo separato per l'inferenza, via QProcess + JSON-lines

L'UI e il motore girano in **due processi**, non due thread.

Motivo: torch può bloccarsi o esaurire memoria in modi che non si
recuperano nello stesso processo, e il GIL rende comunque il threading
inutile qui. Un processo figlio si può **uccidere davvero** quando
l'utente preme Annulla — con un thread non si può.

Comunicazione: il figlio è lanciato con **`QProcess`** e parla con l'UI
in **JSON-lines su stdout** (un oggetto JSON per riga: avanzamento, fase,
errori, risultato). Lo stdin del figlio riceve il `SeparationJob`
serializzato alla partenza e nient'altro.

Perché non `multiprocessing`: dentro un bundle PyInstaller su macOS
`multiprocessing` è fragile (gestione di `freeze_support`, spawn del
binario sbagliato, pickling attraverso il confine del bundle). `QProcess`
si integra nel loop eventi Qt senza thread di polling, e un protocollo
JSON su stdio è banale da testare senza Qt. Nessun socket, nessun HTTP,
nessun server locale.

`worker/protocol.py` definisce i messaggi JSON ed è l'unico posto dove
sono definiti: UI e worker importano entrambi da lì.

### D3 — UI in PySide6 (Qt), non Electron né web

Un solo linguaggio in tutto il progetto. PyInstaller produce un `.app`
nativo. Electron aggiungerebbe 150 MB e un secondo runtime per disegnare
quattro schermate.

**Vincolo anti-degenerazione:** il progetto precedente è morto con un
controller da 3107 righe. Regola dura, verificata in CI (§10.4):
**nessun file supera le 400 righe.** Se cresce, si spacca.

### D4 — Backend di separazione intercambiabili

Il campo si muove in fretta: Demucs oggi, RoFormer domani, altro fra un
anno. Il motore espone un contratto stabile (§5.5) e ogni famiglia di
modelli è un modulo isolato. Cambiare modello non deve toccare UI, export
o data model.

### D5 — L'output è una cartella di WAV più un manifest

Nessun formato proprietario, nessun database, nessuna libreria interna.
Una cartella di file che l'utente può aprire, spostare, trascinare e
cancellare con il Finder. Il `manifest.json` accanto serve all'app per
ripopolare la schermata risultato senza ricalcolare niente.

### D6 — Sviluppo su Windows/CUDA, consegna su Mac Intel/CPU

Lo sviluppo avviene su Windows con GPU NVIDIA. Sul dev-box l'inferenza
gira su CUDA ed è 10–30 volte più veloce che sul target. Regole per non
farsi ingannare:

- Nessun numero di prestazioni misurato su CUDA entra mai nella spec,
  nella UI o nei criteri di uscita. I costi tabellati vengono **solo**
  dalla calibrazione sulla macchina dell'utente (§8.2.1) o da misure sul
  Mac Intel di riferimento.
- La CI esegue il benchmark di scalabilità (§6.3) con `device=cpu` anche
  su Windows: i tempi assoluti non significano nulla, i **rapporti** sì.
- Il codice non contiene alcuna API specifica di piattaforma fuori da
  `ui/` e `packaging/` (§13.3): il motore identico gira su entrambe.

---

## 2. Stack — versioni esatte

Il vincolo che comanda tutto: **l'ultima versione di PyTorch pubblicata
con wheel macOS x86_64 è la 2.2.2.** Versioni successive non esistono per
Mac Intel. L'intero stack è pinnato di conseguenza.

| Componente | Versione | Nota |
|---|---|---|
| Python | **3.11.x** sul target | obbligato: PySide6 6.4 richiede < 3.12. Sul dev-box anche 3.12 |
| PyTorch | **== 2.2.2** | ultima con wheel macOS x86_64 (dichiarano 10.9+); non alzare mai senza cambiare target |
| torchaudio | **== 2.2.2** | pari a torch (wheel 10.13+) |
| numpy | **>= 1.26, < 2** | torch 2.2 è compilato contro numpy 1.x; numpy 2 lo rompe |
| demucs | >= 4.0.1 | verificato compatibile con torch 2.2 |
| soundfile | >= 0.12 | I/O, richiede libsndfile |
| PySide6 | **== 6.4.3** sul target | ultima Qt che gira su macOS < 11; sul dev-box ammessa recente, API comuni |
| pytest | >= 8 | |
| PyInstaller | >= 6.6 | packaging `.app` x86_64; supporta macOS 10.15+ |

Due lock file, uno per piattaforma, entrambi con hash:

- `requirements-macos-x86_64.lock` — quello che conta, usato dal build.
- `requirements-dev-win.lock` — dev su Windows; identico salvo
  `torch==2.2.2+cu121` per l'inferenza CUDA in sviluppo.

`pyproject.toml` per i range. Qualsiasi aggiornamento di torch è vietato
finché il target resta Mac Intel: è il pin più importante del progetto.

---

## 3. Struttura del repository

Da creare esattamente così. I conteggi righe sono tetti, non obiettivi.

```
stemforge/
├── BUILD_SPEC.md                  questo file
├── README.md                      uso, 1 pagina
├── pyproject.toml
├── requirements-macos-x86_64.lock
├── requirements-dev-win.lock
├── Makefile                       dev, test, lint, build, sign
│
├── src/stemforge/
│   ├── __init__.py                __version__
│   │
│   ├── model/                     — dati puri, zero I/O, zero torch
│   │   ├── stem.py                StemKind, StemSpec        (~70)
│   │   ├── job.py                 SeparationJob, JobResult  (~90)
│   │   └── manifest.py            Manifest r/w JSON         (~120)
│   │
│   ├── engine/                    — separazione
│   │   ├── contract.py            Backend Protocol, Quality (~90)
│   │   ├── registry.py            nome -> backend           (~60)
│   │   ├── planner.py             stem -> piano passate     (~170)
│   │   ├── demucs4.py             backend Demucs v4         (~180)
│   │   ├── drumsplit.py           2° stadio batteria (M6)   (~150)
│   │   ├── vocalsplit.py          2° stadio lead/cori (M6)  (~130)
│   │   ├── dereverb.py            de-riverbero voce (M6)    (~120)
│   │   ├── roformer.py            backend RoFormer (M4)     (~180)
│   │   ├── device.py              CUDA / CPU                (~70)
│   │   ├── calibrate.py           micro-benchmark 1° avvio  (~90)
│   │   └── audio_io.py            load, resample, write     (~130)
│   │
│   ├── worker/                    — processo figlio
│   │   ├── protocol.py            messaggi JSON UI <-> worker (~90)
│   │   └── runner.py              entry point del figlio    (~150)
│   │
│   ├── export/
│   │   └── folder.py              WAV + manifest            (~110)
│   │
│   ├── ui/                        — Qt, nessuna logica
│   │   ├── app.py                 bootstrap                 (~90)
│   │   ├── main_window.py         shell + routing           (~200)
│   │   ├── drop_zone.py           schermata 1               (~150)
│   │   ├── stem_picker.py         schermata 2               (~220)
│   │   ├── stem_group.py          blocco a fisarmonica      (~120)
│   │   ├── progress_view.py       schermata 3               (~160)
│   │   ├── result_view.py         schermata 4 + drag out    (~200)
│   │   ├── bridge.py              QProcess <-> worker       (~180)
│   │   └── theme.py               colori, font              (~80)
│   │
│   └── cli.py                     stessa pipeline, headless (~130)
│
├── tests/
│   ├── fixtures/                  8 s di audio sintetico, no copyright
│   ├── unit/
│   └── integration/
│
└── packaging/
    ├── stemforge.spec             PyInstaller, x86_64
    ├── entitlements.plist
    └── notarize.sh
```

**Dipendenze fra livelli — direzione unica, verificata in CI:**

```
ui  ->  worker  ->  engine  ->  model
export ->  model
```

`model` non importa nulla del progetto. `engine` non importa `ui`. Se `ui`
compare in un import di `engine`, la build fallisce.

---

## 4. Modello dati

### 4.1 `StemKind`

Due livelli. I **base** escono dal primo stadio, i **derivati** dal secondo
(§5.2) e si ottengono lavorando su uno stem base già pulito.

```python
class StemKind(StrEnum):
    # base — primo stadio (§5.1)
    VOCALS       = "vocals"
    DRUMS        = "drums"
    BASS         = "bass"
    GUITAR       = "guitar"
    PIANO        = "piano"
    OTHER        = "other"
    INSTRUMENTAL = "instrumental"    # mix meno vocals, per sottrazione

    # derivati da DRUMS — secondo stadio
    KICK    = "kick"
    SNARE   = "snare"
    TOMS    = "toms"
    HIHAT   = "hihat"
    CYMBALS = "cymbals"

    # derivati da VOCALS — secondo stadio
    LEAD_VOCALS    = "lead_vocals"
    BACKING_VOCALS = "backing_vocals"
```

Tutto ciò che non ricade in queste categorie — archi, fiati, synth,
tastiere, percussioni accessorie — finisce in `other`, che è il residuo per
costruzione. **Non se ne parla nell'interfaccia**: non c'è una casella
"archi" disabilitata, non c'è una nota che spiega perché mancano. `other`
è semplicemente ciò che resta.

`INSTRUMENTAL` è gratis: è `mix - vocals`, calcolato per sottrazione senza
alcuna inferenza aggiuntiva.

### 4.1.1 `StemSpec` — la tabella delle dipendenze

```python
@dataclass(frozen=True)
class StemSpec:
    kind: StemKind
    stage: int                    # 1 = base, 2 = derivato
    derives_from: StemKind | None # None per i base
    label: str                    # nome mostrato nell'UI
```

Il grafo delle dipendenze è ciò che permette al pianificatore (§5.3) di
sapere che chiedere `kick` implica calcolare `drums`, anche se l'utente
non ha spuntato `drums`.

### 4.2 `SeparationJob`

```python
@dataclass(frozen=True)
class SeparationJob:
    source: Path
    wanted: tuple[StemKind, ...]
    quality: str              # "fast" | "balanced" | "best"
    out_dir: Path
    fmt: str                  # "wav" | "flac"
    device: str               # "auto" | "cpu" | "cuda"
    dereverb_vocals: bool = False   # §5.2.3, opzione non stem
```

`device="auto"` sceglie CUDA se disponibile (dev-box Windows), altrimenti
CPU (target Mac Intel). Non esiste il caso MPS: il target non lo ha.

Immutabile. Serializzabile in JSON (attraversa il confine fra processi
come primo messaggio su stdin del worker, vedi D2).

### 4.3 `manifest.json` — contratto stabile

Scritto accanto agli stem.

```json
{
  "schema": 1,
  "source": { "name": "brano.mp3", "sha1": "…", "duration_s": 214.7 },
  "audio":  { "samplerate": 44100, "channels": 2, "bit_depth": 24 },
  "engine": { "backend": "demucs", "model": "htdemucs_ft",
              "quality": "best", "version": "0.1.0" },
  "stems": [
    { "kind": "vocals", "file": "vocals.wav",
      "peak_dbfs": -1.2, "rms_dbfs": -18.4 }
  ],
  "created_utc": "2026-08-10T14:22:31Z"
}
```

`schema` va incrementato a ogni cambio incompatibile; i reader rifiutano
uno schema che non conoscono con un errore chiaro.

---

## 5. Il motore di separazione

### 5.1 Primo stadio — scelta del modello

| Se l'utente chiede | Modello | Stem prodotti |
|---|---|---|
| solo voce/batteria/basso/altro | `htdemucs_ft` | 4 |
| anche chitarra o piano | `htdemucs_6s` | 6 |

`htdemucs_ft` è più pulito sui quattro classici, quindi va preferito quando
basta. La scelta è automatica: l'utente spunta gli strumenti, l'app decide
il modello e non gliene parla.

Gli stem non richiesti non vengono scritti su disco, ma sono comunque
sommati dentro `other`, per preservare l'invariante di §10.2.

### 5.1.1 L'ottimizzazione che rende conveniente chiedere poco

`htdemucs_ft` non è un modello: è un **insieme di quattro modelli
specializzati** (un `BagOfModels`, uno fine-tuned per sorgente) che
vengono eseguiti tutti e combinati con pesi che di fatto assegnano a ogni
sotto-modello la sua sorgente. È da lì che viene la sua qualità superiore,
ed è da lì che viene il suo costo: quattro inferenze complete.

**Se l'utente chiede un solo stem base, si esegue soltanto il sotto-modello
specializzato in quella sorgente.** Chi vuole solo la voce paga circa un
quarto del tempo, e la ottiene alla stessa qualità — perché il sotto-modello
della voce è esattamente ciò che rende `htdemucs_ft` buono sulla voce.

Regola di attivazione, valida per i preset `fast` e `balanced`:

| Stem base richiesti | Esecuzione |
|---|---|
| 1 (più eventuale `other`/`instrumental`) | **solo** il sotto-modello corrispondente |
| 2 o 3 | i sotto-modelli corrispondenti |
| 4 | insieme completo, come oggi |

**Nel preset `best` l'insieme completo viene sempre eseguito**, qualunque
cosa sia stata richiesta. È la traduzione diretta della priorità del
committente: in `best` non esiste alcuna scorciatoia, nemmeno una
dimostrabilmente inudibile. Chi vuole la garanzia assoluta la ha; chi
vuole il lavoro veloce usa `fast`/`balanced` e ottiene la scalabilità.

Il complemento si ricava per sottrazione: `other = mix − stem_richiesti`.
La sottrazione è esatta, quindi l'invariante di §10.2 regge per costruzione
— anzi, regge *meglio* del caso completo.

**Verifica obbligatoria** (`tests/integration/test_single_source.py`): lo
stem prodotto dal solo sotto-modello va confrontato con quello prodotto
dall'insieme completo a parità di preset. Differenza attesa sotto
−25 dBFS RMS. Il test documenta anche il rapporto dei tempi misurati.

Su `htdemucs_6s` questa ottimizzazione **non si applica** — non è un
insieme, è un modello singolo a sei uscite. Chiedere chitarra o piano costa
sempre una passata intera.

### 5.2 Secondo stadio — stem derivati

Gira **solo se** l'utente ha chiesto almeno uno stem derivato, e opera
**solo** sullo stem base da cui deriva, mai sul mix.

È la ragione per cui questi tre funzionano dove archi e fiati falliscono:
hanno davanti un problema molto più facile, perché il materiale su cui
lavorano è già stato ripulito dal primo stadio.

```
                  ┌─ vocals ──[ 2° stadio ]──┬─ lead_vocals
                  │                          └─ backing_vocals
  MIX ──[ 1° ]────┼─ drums ───[ 2° stadio ]──┬─ kick
                  │                          ├─ snare
                  ├─ bass                    ├─ toms
                  ├─ guitar                  ├─ hihat
                  ├─ piano                   └─ cymbals
                  └─ other
```

I modelli concreti, le fonti e le licenze del secondo stadio sono fissati
in §5.8.

#### 5.2.1 Batteria → kick / snare / toms / hihat / cymbals

Il derivato con la resa migliore. I colpi di batteria sono transienti
spettralmente distinti e temporalmente sparsi: è il caso più favorevole che
esista per una separazione.

- Backend dedicato in `engine/drumsplit.py`, contratto identico a §5.5.
- Ingresso: lo stem `drums` a 44100 Hz. Mai il mix.
- Il residuo (rullantini, percussioni non riconosciute, riverbero della
  stanza) rientra in un `drums_other` che **non** viene scritto separatamente
  ma sommato allo stem `drums` se richiesto, o a `other` altrimenti.
- Costo: una passata su un solo stem, cioè una frazione del primo stadio.

#### 5.2.2 Voce → lead / cori

Modello di tipo "karaoke" applicato allo stem `vocals`. Separa la linea
principale dalle armonizzazioni e dai raddoppi.

Limite da conoscere: sui **raddoppi all'unisono** della stessa voce la
separazione è debole, perché non c'è quasi nulla che distingua le due
tracce. Funziona bene sulle armonizzazioni a intervalli. Non è un caso da
gestire nel codice, è un fatto da non sorprendersi di trovare.

#### 5.2.3 Voce → de-riverbero

Non produce uno stem: **modifica** lo stem `vocals`. Toglie riverbero e
delay, restituendo una voce asciutta, molto più utile da ricampionare.

- È una **casella opzionale** accanto alla voce, non uno strumento nella
  griglia.
- Quando attiva, `vocals.wav` è la versione asciutta e viene scritto anche
  `vocals_wet.wav` con l'originale. L'utente non deve mai perdere il
  materiale non trattato.
- **Rompe l'invariante di ricostruzione**, ed è l'unica cosa in tutta la
  spec che può farlo: il riverbero rimosso non è più nella somma. Il test
  di §10.2 deve girare sulla versione `_wet` quando l'opzione è attiva.
  Segnare nel manifest `"dereverb": true`.

#### 5.2.4 Regola comune ai derivati

Se un modello di secondo stadio non è disponibile o fallisce, **lo stem
base sopravvive**. L'utente ottiene `drums.wav` invece di kick e snare, con
un avviso non bloccante. Non si perde mai il lavoro del primo stadio per
colpa del secondo.

### 5.3 Pianificatore — il tempo scala con quanto si chiede

Il punto di questa sezione: **chiedere una traccia sola deve costare una
frazione di chiedere tutto**, non lo stesso tempo con meno file in uscita.
Su una macchina dove "tutto" costa mezz'ora, questa non è
un'ottimizzazione: è ciò che rende l'app usabile per il lavoro quotidiano.

Il pianificatore riceve gli stem richiesti e produce un piano di esecuzione:

1. **Chiusura delle dipendenze.** Per ogni derivato richiesto, aggiungere il
   suo `derives_from`. Chi chiede `kick` fa calcolare `drums` anche senza
   averlo spuntato — ma `drums.wav` viene scritto solo se richiesto
   esplicitamente.
2. **Scelta del modello di 1° stadio** (§5.1): `6s` solo se servono chitarra
   o piano.
3. **Applicazione di §5.1.1** se i base sono tre o meno, il modello è `ft`
   e il preset non è `best`.
4. **Elenco delle passate di 2° stadio**, una per stem base coinvolto.
5. **Stima del tempo** = somma dei costi di ogni passata, dove ogni passata
   ha un costo per secondo di audio preso dalla **tabella di calibrazione
   della macchina** (§8.2.1), mai da costanti scritte nel codice.

Il piano è un oggetto ispezionabile e **testabile senza torch**: dato un
insieme di stem richiesti, produce un elenco di passate. È il pezzo di
logica con più casi limite di tutto il progetto e va coperto da test
unitari esaustivi, non da test di integrazione lenti.

### 5.4 Tempi — cosa aspettarsi e cosa è vincolante

**Nessun numero assoluto in questa sezione è un vincolo.** Su Mac Intel i
tempi dipendono ferocemente da generazione della CPU, numero di core e
stato termico della macchina. I numeri veri li produce la calibrazione al
primo avvio (§8.2.1); quelli qui sotto servono solo a dimensionare le
aspettative durante lo sviluppo.

Ordine di grandezza atteso — Mac Intel quad-core ~2015-2019, brano 4 min,
preset `balanced`:

| Richiesta | Passate | Ordine di grandezza |
|---|---|---|
| solo `vocals` | 1 sotto-modello | minuti (pochi) |
| `vocals` + `instrumental` | 1 sotto-modello + sottrazione | come sopra |
| `vocals` + `drums` | 2 sotto-modelli | ~2× il caso singolo |
| i 4 base | insieme completo | ~4× il caso singolo |
| i 6 base (con chitarra/piano) | `6s`, passata singola | fra 1× e 4× |
| 4 base + tutti i derivati | completo + 3 passate corte | poco più del completo |
| qualsiasi cosa in `best` | insieme completo, shifts=2 | **~3× il `balanced` completo** — anche ore, ed è accettato |

**Ciò che è vincolante** (verificato in §6.3): il rapporto fra la
richiesta minima (`vocals` in `balanced`) e la massima (tutto in
`balanced`) deve restare vicino a 1:4 in tempo misurato. Se la scalabilità
si perde, O7 è violato e la build fallisce.

Alla chiusura di M1 la tabella va **riempita con i tempi misurati sul Mac
Intel di riferimento** e riportata nel README, così l'utente sa cosa
aspettarsi prima ancora di aprire l'app.

### 5.5 Contratto `Backend`

```python
class Backend(Protocol):
    name: str
    provides: frozenset[StemKind]
    samplerate: int

    def separate(
        self,
        audio: Tensor,                # [channels, samples] float32
        wanted: frozenset[StemKind],
        on_progress: Callable[[float], None],
        should_cancel: Callable[[], bool],
    ) -> dict[StemKind, Tensor]: ...
```

Tre punti non negoziabili:

- **La garanzia di annullamento entro 1 secondo la dà l'uccisione del
  processo figlio** (D2), non questo contratto: su CPU un singolo segmento
  può richiedere più di un secondo di calcolo, quindi nessun controllo
  cooperativo può garantire quella latenza.
- `should_cancel` va comunque consultato **fra un segmento e l'altro**:
  serve alla terminazione *pulita* (nessun file parziale, nessun tensore
  orfano) quando l'annullo arriva in un momento comodo. Il kill resta il
  paracadute, non il percorso normale.
- `on_progress` riceve 0.0–1.0 monotòno crescente. Mai all'indietro.

### 5.6 Preset qualità

```python
@dataclass(frozen=True)
class Quality:
    overlap: float
    shifts: int
    half: bool           # solo CUDA; su CPU sempre False
    segment_s: float | None
```

| Preset | overlap | shifts | segment | Uso |
|---|---|---|---|---|
| `fast` | 0.05 | 0 | 7.8 | anteprima, batch esplorativo |
| `balanced` | 0.10 | 0 | 7.8 | lavoro veloce con scalabilità §5.1.1 |
| `best` | 0.25 | 2 | 7.8 | **default** — consegna, nessuna scorciatoia |

Perché questi numeri:

- **Il default è `best`.** Priorità del committente: la qualità prima del
  tempo. Chi apre l'app e preme Separa senza toccare nulla ottiene il
  massimo che i modelli sanno dare, con la stima onesta dell'attesa
  davanti agli occhi (§8.2.1). `balanced` esiste per chi ha fretta e lo
  sceglie consapevolmente.
- **`shifts=2` sta solo in `best`.** Ogni shift è un'inferenza completa in
  più per una frazione di dB: in `best` quella frazione la vogliamo, negli
  altri preset sarebbe tempo rubato alla scalabilità.
- **`overlap` oltre 0.25 non serve a niente**, e sotto 0.05 iniziano a
  sentirsi le giunzioni. Il costo è lineare.
- **`half` (fp16) è un fatto solo di sviluppo:** vale su CUDA. Sul target
  (CPU) fp16 è emulato e più lento, quindi è **sempre `False` quando
  `device == "cpu"`**, qualunque cosa dica il preset. Sul target i preset
  differiscono solo per `overlap` e `shifts`.
- **`segment` resta 7.8 anche in `best`:** aumentarlo alza la RAM in modo
  quadratico e su un Mac Intel da 8 GB fa swappare, che distrugge i tempi
  senza aggiungere qualità.

### 5.7 I/O audio — regole

1. Decodifica sempre a **float32**, mai int.
2. I modelli girano a **44100 Hz**. Se la sorgente ha un altro sample rate,
   resample in ingresso e **resample indietro in uscita**: l'utente deve
   riavere il suo sample rate originale, o gli stem non si allineeranno una
   volta trascinati nel progetto. Dopo il round-trip di resampling, ogni
   stem va **troncato o azzerato-in-coda alla lunghezza esatta in campioni
   del sorgente**: un resampler può sbagliare di qualche campione, e anche
   un solo campione di differenza è un bug (§10.2).
3. Mono in ingresso → duplicato su due canali per il modello → **riscritto
   mono** in uscita.
4. Scrittura a **24 bit PCM** di default, sia WAV che FLAC. Mai 16 bit:
   gli stem hanno headroom bassa e il quantization noise si sente quando
   li rialzi.
5. **Nessuna normalizzazione, nessun limiting, nessun fade.** Se la somma
   degli stem non ricostruisce il mix (entro l'errore del modello), è un
   bug. La DAW è il posto dove si mixa.
6. File > 15 minuti: elaborare a blocchi con **overlap-add a finestre
   complementari** — le due rampe di dissolvenza devono sommare
   esattamente a 1 in ogni campione della zona di sovrapposizione
   (rampe lineari complementari: `w` e `1-w`). Un crossfade generico
   (es. equal-power) non somma a 1 e romperebbe l'invariante di §10.2
   proprio sui file lunghi, dove nessuno esegue mai il test. Limite duro
   30 minuti, oltre il quale si rifiuta con messaggio chiaro.

### 5.8 Modelli, pesi e licenze — la tabella delle decisioni

Il primo stadio è deciso e senza rischi:

| Uso | Modello | Fonte pesi | Licenza |
|---|---|---|---|
| 1° stadio, 4 stem | `htdemucs_ft` | `dl.fbaipublicfiles.com` (remote ufficiale demucs) | MIT |
| 1° stadio, 6 stem | `htdemucs_6s` | come sopra | MIT |

Per il 2° stadio (M6) e RoFormer (M4) i pesi migliori vengono dalla
community e le licenze **variano e vanno verificate una per una**. La spec
fissa i candidati e la procedura, non finge che la scelta sia già chiusa:

| Uso | Candidato primario | Candidato di riserva | Stato licenza |
|---|---|---|---|
| Split batteria | modello drum-sep della famiglia Demucs fine-tuned (es. "DrumSep") | LarsNet (Politecnico di Milano) | da verificare; LarsNet è CC BY-NC 4.0 |
| Lead / cori | modello karaoke MDX/RoFormer della scena UVR | modello BVE UVR | da verificare, molti sono non-commercial |
| De-riverbero | modello De-Echo/De-Reverb della scena UVR | — | da verificare |
| RoFormer voce (M4) | BS-RoFormer (checkpoint community ad alto SDR) | Mel-RoFormer | da verificare |

Regole vincolanti:

1. **Selezione a inizio milestone, non in corsa.** All'apertura di M4 e di
   M6 si fa un A/B su 3 brani reali fra primario e riserva; vince
   l'ascolto, si verbalizza la scelta nel commit.
2. **Ogni peso adottato viene fissato con URL a revisione immutabile**
   (commit hash se hosted su HuggingFace) **e SHA-256 registrato nel
   codice** accanto agli altri (§9.2). Niente URL "latest".
3. **Uso personale vs distribuzione.** Finché l'app è per uso personale
   (firma ad-hoc, §9.3), i pesi non-commercial sono accettabili. La
   checklist di `notarize.sh` — cioè il percorso di distribuzione a terzi —
   include un controllo bloccante: nessun peso con licenza non-commercial
   o non chiara può essere referenziato da una build distribuita.
4. **RoFormer su CPU Intel è molto più lento di Demucs.** Resta in scope
   (il committente accetta l'attesa), ma la stima di §8.2.1 deve
   calibrarlo separatamente: la sua voce di costo non si deriva da quella
   di Demucs.

---

## 6. Prestazioni e memoria

Su questo target la parola "prestazioni" cambia significato: non si
insegue un tetto di secondi, si insegue **non sprecare** e **non
esaurire la RAM**. Lo spreco si misura; l'attesa legittima no.

### 6.1 Cosa conta, in ordine

1. **Eseguire solo ciò che è stato chiesto** (§5.1.1 + pianificatore).
   Sul target è la differenza fra minuti e mezz'ore: è la leva numero uno
   e non ha costi di qualità nei preset dove si applica.
2. **Caricare ogni modello una volta sola** per l'intero job, batch
   compreso. In un batch da 20 file il caricamento ripetuto è metà del
   tempo totale.
3. **Disciplina di RAM.** fp32 su CPU con l'insieme `ft`: caricare i
   sotto-modelli **in sequenza, uno alla volta**, liberando i tensori del
   precedente prima di caricare il successivo. Un Mac Intel da 8 GB che
   swappa è l'unico modo di trasformare "lento ma va" in "non finisce
   mai".
4. **Decodifica del file successivo mentre il corrente è in inferenza** —
   utile solo su batch, ~5%. Farlo per ultimo.

### 6.2 Cosa NON fare

- Non mettere `torch.compile`: su torch 2.2/CPU costa più in compilazione
  di quanto restituisca su un brano solo.
- Non aumentare `segment` per "andare più veloce": alza la RAM in modo
  quadratico e su 8 GB fa swappare, che è molto peggio.
- Non parallelizzare due brani: si contendono core e memoria e vanno
  entrambi più piano della somma in serie. Vale su CPU ancora più che su
  GPU.
- Non forzare fp16 su CPU (§5.6): è emulato, più lento e senza benefici.
- Non "ottimizzare" tagliando `shifts` o `overlap` in `best`: la lentezza
  di `best` è un costo accettato, non un difetto da correggere.

### 6.3 Benchmark — che cosa fallisce la build e che cosa no

`tests/integration/test_perf.py`, con `device=cpu` su qualunque macchina:

- **Vincolante — scalabilità (O7):** tempo di (`vocals`, `balanced`)
  diviso tempo di (4 base, `balanced`) deve stare sotto **0.35**. È un
  rapporto, quindi è significativo anche sul dev-box.
- **Vincolante — nessuna regressione relativa:** i rapporti fra i preset
  (`fast` < `balanced` < `best`) devono rispettare l'ordine e restare
  entro il 25% dei rapporti registrati alla baseline.
- **Informativo — tempi assoluti:** misurati e stampati nel report, mai
  causa di fallimento. I valori misurati sul Mac Intel di riferimento
  vanno copiati nel README a ogni release.

---

## 7. Consegna alla DAW

### 7.0 Perché non un plugin

Un plugin gira nel thread audio della DAW, con un budget di pochi
millisecondi per buffer e il divieto assoluto di allocare memoria. La
separazione neurale richiede **minuti** e gigabyte di RAM. Non è
una limitazione dell'implementazione: è incompatibilità di natura. Ogni
prodotto che offre separazione "in un plugin" in realtà fa esattamente
quello che facciamo qui — elabora offline e consegna file.

### 7.1 Il drag & drop è l'unico meccanismo di trasporto

L'utente ha già il suo progetto aperto, con le sue tracce, il suo tempo, il
suo lavoro dentro. Trascina lo stem dove gli serve e continua. È il flusso
più corto possibile: nessun import, nessun salvataggio, nessun progetto
nuovo da aprire e poi riconciliare con quello vero.

Funziona con **tutte** le DAW senza scrivere una riga di codice specifica
per nessuna di esse, perché è il meccanismo nativo di macOS.

### 7.2 Implementazione

Nella schermata risultato (§8.4), ogni riga stem è una sorgente di drag:

```python
drag = QDrag(widget)
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(path)) for path in selected_paths])
drag.setMimeData(mime)
drag.exec(Qt.DropAction.CopyAction)
```

Requisiti:

- **Selezione multipla trascinabile in un colpo solo.** Trascinare quattro
  stem uno alla volta è la scocciatura che questa funzione deve evitare.
  `setUrls` accetta una lista: Ableton crea una traccia per file.
- **Percorsi assoluti e file già chiusi** prima che il drag sia possibile.
  Trascinare un file ancora in scrittura dà un import troncato.
- **Feedback visivo**: icona di trascinamento con il numero di file
  (`drag.setPixmap`).
- L'azione è **Copy**, mai Move: il file deve restare nella cartella di
  output anche dopo il drop.

### 7.3 Layout su disco

```
~/Music/StemForge/Brano/
  vocals.wav
  drums.wav
  bass.wav
  other.wav
  manifest.json
```

Nome cartella = nome del file sorgente senza estensione. In caso di
collisione, suffisso ` (2)`, mai sovrascrittura silenziosa.

Nomi file uguali al valore di `StemKind`: minuscoli, senza spazi, senza il
nome del brano ripetuto dentro. Ableton mostra il nome del file come nome
della traccia, quindi `vocals.wav` diventa una traccia chiamata `vocals` —
che è esattamente ciò che serve.

### 7.4 Rivelazione nel Finder

Pulsante `Mostra nel Finder` che apre la cartella con lo stem selezionato
già evidenziato. Serve a chi preferisce trascinare dal Finder, o vuole
copiare i file altrove.

---

## 8. Interfaccia

Quattro schermate. Nient'altro. Nessun menu di preferenze annidato.

### 8.1 Schermata 1 — Drop

Una zona grande al centro: *"Trascina un brano, o scegli un file."*
Accetta `wav mp3 flac ogg m4a aiff aif`, file multipli, cartelle.
File non audio: rifiutati con messaggio inline, senza dialog modale.

### 8.2 Schermata 2 — Scelta strumenti

È la schermata dove l'utente decide quanto tempo vuole spendere. Deve
rendere quel legame evidente senza spiegarlo a parole.

**Riga 0 — le due scorciatoie**, in cima, grandi:
`Tutto` e `Solo voce`. Sono gli estremi che si usano il 90% delle volte:
la resa completa e il lavoro veloce. Un click, non sei.
`Solo voce` imposta anche il preset su `balanced`: è la scorciatoia del
lavoro veloce, e la scalabilità di §5.1.1 vive lì. `Tutto` lascia `best`.

**Blocco 1 — Strumenti.** Sette card: voce, batteria, basso, chitarra,
piano, altro, strumentale. Icona, nome, checkbox.
Voce, batteria, basso e altro preselezionati.

**Blocco 2 — Dettaglio batteria**, sotto la card batteria, chiuso a
fisarmonica. Kick, snare, toms, hi-hat, cymbals. Aprirlo e spuntarne uno
seleziona automaticamente la batteria come dipendenza (§5.3).

**Blocco 3 — Dettaglio voce**, stessa forma. Lead, cori, e la casella
`Togli il riverbero` — che è un'opzione, non uno strumento, e va graficamente
distinta dalle altre.

I due blocchi a fisarmonica restano **chiusi di default**: chi vuole i
quattro stem classici non deve nemmeno vederli.

**In fondo** due soli controlli: **preset qualità** (default `best`) e
**formato**.

#### 8.2.1 La stima del tempo — onesta perché calibrata

Sempre visibile, in basso, aggiornata dal vivo a ogni spunta. Viene dal
pianificatore (§5.3), non da una formula approssimata nell'UI: è la somma
reale delle passate che verranno eseguite.

I costi unitari (secondi di calcolo per secondo di audio, per modello e
per preset) **non sono costanti nel codice**: le macchine Intel variano
troppo. Al primo avvio, dopo il download dei pesi, `engine/calibrate.py`
esegue un micro-benchmark (~10 s di audio sintetico attraverso il
sotto-modello vocals e una passata di 2° stadio se installata) e salva la
tabella dei costi in
`~/Library/Application Support/StemForge/calibration.json`. Ogni job
completato aggiorna la tabella con una media mobile: la stima migliora
con l'uso.

- **Deve scendere quando si toglie roba**, e visibilmente. È il feedback che
  insegna all'utente che chiedere meno costa meno — senza quel feedback,
  l'ottimizzazione di §5.1.1 esiste ma nessuno la sfrutta.
- Va **sovrastimata del 15%**: finire prima del previsto è un piacere, dopo
  è un difetto.
- Accanto, il numero di passate in chiaro: *"~14 min · 4 passate"*.
- Con il default `best` su un Mac vecchio la stima dirà anche "più di
  un'ora". **Va mostrata lo stesso, senza eufemismi**: è la scelta O5.
  L'utente che la trova eccessiva ha `balanced` a un click di distanza.

### 8.3 Schermata 3 — Avanzamento

- Barra 0–100% con la fase corrente in parole: *"Separazione — passata 2
  di 3"*, *"Dettaglio batteria"*, *"Scrittura stem"*.
- Con più passate, l'avanzamento globale è la **somma pesata** dei costi
  stimati di ciascuna, non la media semplice: le passate di 2° stadio sono
  molto più corte della prima e una barra che le trattasse alla pari
  sembrerebbe bloccata all'inizio e poi scattante alla fine.
- Tempo rimanente, aggiornato ogni 2 s, con media mobile per non farlo
  saltellare. Su attese lunghe (oltre 10 min) mostrare anche l'orario
  previsto di fine: *"~35 min — pronto verso le 15:40"*.
- **Pulsante Annulla sempre attivo**, che uccide il processo figlio entro
  1 secondo e ripulisce i file parziali.

### 8.4 Schermata 4 — Risultato

Questa è la schermata che conta, perché è quella da cui si trascina.

- Elenco stem con durata e picco dBFS.
- **Preview di ascolto**: play/stop, un solo stem alla volta. Niente
  mixer, niente solo/mute: quella è la DAW.
- **Ogni riga è trascinabile, e la selezione multipla si trascina insieme**
  (§7.2). È la funzione principale dell'app: deve essere ovvia a colpo
  d'occhio, non nascosta.
- `Mostra nel Finder`.
- La finestra deve restare utilizzabile mentre Ableton è in primo piano —
  niente `WindowStaysOnTop` forzato, ma nemmeno una finestra che sparisce
  dietro la DAW appena perde il fuoco. Il drag parte da una finestra non
  attiva: verificare che funzioni al **primo** click-e-trascina, senza un
  click preliminare per dare il fuoco.

### 8.5 Regole per non ripetere l'errore del vecchio progetto

- **Nessun file UI oltre 400 righe.**
- I widget **non conoscono** `engine`. Parlano solo con `bridge.py`.
- Nessuna logica di business in un widget: se una classe UI importa torch o
  soundfile, è un errore di architettura.
- Nessun `QThread` per l'inferenza: si usa il processo figlio (D2).

---

## 9. App standalone su macOS

### 9.1 Build

PyInstaller, `packaging/stemforge.spec`:

- **`target_arch = "x86_64"`.** Il target è il Mac Intel. Universal2
  resta escluso: richiederebbe una toolchain doppia per torch — che per
  arm64 avrebbe comunque versioni diverse, visto il pin 2.2.2 — e non
  serve a nessuno degli utenti previsti. Bonus non garantito: un `.app`
  x86_64 gira anche su Apple Silicon via Rosetta 2, ma non è un target
  supportato né testato.
- Escludere `matplotlib`, `tkinter`, `IPython`, `pytest` e ogni backend Qt
  non usato. Senza esclusioni il bundle passa 1 GB.
- `.app` con `Info.plist` che dichiara i tipi di file audio in
  `CFBundleDocumentTypes`, così "Apri con" funziona dal Finder.
- `LSMinimumSystemVersion = 10.15`. Nota di contesto: Apple sta chiudendo
  il supporto Intel (macOS 26 è l'ultima major per Intel). Non cambia
  nulla per la v1 — l'app gira offline e continuerà a girare — ma è il
  motivo per cui §13.2 (CoreML) su questo target non promette molto:
  senza Neural Engine, CoreML girerebbe comunque su CPU.

### 9.2 I pesi dei modelli

**Non impacchettare i pesi nell'app** (htdemucs_ft è ~700 MB in quattro
file). Scaricarli al primo avvio, con barra di avanzamento e destinazione
`~/Library/Application Support/StemForge/models/`.

Fonti di download:

- Pesi Demucs: il **remote ufficiale** (`dl.fbaipublicfiles.com`), stesso
  usato dal pacchetto demucs. URL completi fissati nel codice.
- Pesi di 2° stadio e RoFormer: URL a **revisione immutabile** secondo le
  regole di §5.8 — mai un link "latest", mai un link a un file che il
  proprietario del repo può sostituire in silenzio.

Verificare **SHA-256** di ogni file scaricato contro una lista fissata nel
codice. Un peso corrotto a metà download deve essere riconosciuto e
riscaricato, non caricato.

Se non c'è rete al primo avvio: messaggio esplicito che serve la
connessione **una sola volta**, poi l'app è offline per sempre.

### 9.3 Firma

Per uso personale basta la firma ad-hoc, poi click destro → Apri la prima
volta. **Niente `--deep`**: è deprecato e inaffidabile su bundle con
centinaia di dylib come quelli PyInstaller. Si passa l'identità a
PyInstaller (`codesign_identity` nello spec file), che firma la gerarchia
dall'interno verso l'esterno; per l'ad-hoc, identità `-`.

Per distribuire a terzi serve un Apple Developer Program (99 $/anno):
Developer ID, hardened runtime, `entitlements.plist` con
`com.apple.security.cs.allow-unsigned-executable-memory` (torch ne ha
bisogno), poi `notarytool submit --wait` e `stapler staple`.
`packaging/notarize.sh` va scritto ma **non** invocato dalla build di
default, e include il controllo licenze di §5.8 punto 3: una build con
pesi non-commercial non può uscire da quella porta.

### 9.4 Primo avvio

Sequenza: controllo pesi → download se mancano → **calibrazione**
(§8.2.1, con una riga di spiegazione: "Misuro la velocità di questo Mac
per darti stime oneste") → finestra principale.
Mai una finestra vuota mentre si scaricano 700 MB in silenzio.

---

## 10. Errori e test

### 10.1 Regole sugli errori

1. **Ogni errore mostrato all'utente dice cosa fare.** "Errore di
   separazione" è vietato. "Memoria insufficiente: chiudi altre app o passa
   al preset Veloce" è accettabile.
2. Traceback completo nel log, **mai** in faccia all'utente.
3. Log in `~/Library/Logs/StemForge/stemforge.log`, rotazione a 5 MB × 3.
4. Un file che fallisce in un batch **non ferma gli altri**. Riepilogo alla
   fine.

| Caso | Comportamento |
|---|---|
| File audio corrotto | salta, messaggio con nome file, continua il batch |
| Formato non supportato | rifiuta al drop, non a metà elaborazione |
| Traccia silenziosa (< −60 dBFS) | scrive comunque, avvisa "quasi silenzioso" |
| RAM esaurita | messaggio chiaro: chiudere altre app o usare `fast`; il job si può rilanciare |
| Disco pieno | controlla lo spazio **prima** di iniziare; la stima viene dal piano: `n_stem_scritti × durata × byterate` (24 bit stereo ≈ 15 MB/min per stem) + 20% di margine, non un fattore fisso |
| Annulla a metà | uccide il figlio, cancella i parziali, torna alla schermata 2 con le scelte intatte |
| Modello non scaricabile | messaggio con causa di rete, riprovabile |
| Brano > 30 min | rifiuta con motivazione esplicita |

### 10.2 Invariante di ricostruzione — il test più importante

Su un fixture sintetico di 8 secondi (sinusoide + rumore + click, generato
in codice, zero materiale protetto da copyright):

```
somma(stem) - mix_originale  ->  RMS < -40 dBFS
```

Se questo test fallisce, qualcosa nella catena sta normalizzando,
ritardando o scalando l'audio. È la rete di sicurezza contro l'intera
classe di bug più insidiosa.

Verificare anche: **lunghezza in campioni identica** al sorgente (uno
sfasamento di anche un solo campione manda fuori sync lo stem una volta
trascinato nel progetto), e sample rate identico. La verifica di
lunghezza va fatta anche su un fixture a **48000 Hz**, per coprire il
round-trip di resampling di §5.7 punto 2.

L'invariante vale **a ogni livello dell'albero**: se sono stati prodotti
kick, snare, toms, hi-hat e cymbals, la loro somma più il residuo deve
ricostruire `drums`. Unica eccezione ammessa in tutta la spec: il
de-riverbero (§5.2.3), che va testato sulla versione `_wet`.

### 10.3 Unitari e integrazione

Unitari senza torch, veloci: `model/`, `manifest`, `device`, parsing CLI,
naming e collisioni di cartella, protocollo JSON del worker. Tempo totale
**< 5 secondi**.

**Il pianificatore (§5.3) va coperto in modo esaustivo**, ed è il test
unitario più importante del progetto perché è dove si annidano i casi
limite: chiedere `kick` senza `drums`; chiedere `lead_vocals` con
`dereverb` attivo; chiedere solo `instrumental`; chiedere un derivato di
`drums` e uno di `vocals` insieme; chiedere tutto; **chiedere un solo stem
in `best` e verificare che il piano usi l'insieme completo** (§5.1.1);
lo stesso in `balanced` e verificare che usi il sotto-modello. Per ognuno
si verifica il modello di 1° stadio scelto, l'elenco esatto delle passate,
e quali file finiscono su disco. Gira senza torch, in millisecondi.

Integrazione: pipeline completa con backend finto (< 10 s); pipeline con
Demucs reale marcata `@pytest.mark.slow`; annullamento che uccide il
processo entro 1 s senza lasciare parziali; benchmark di scalabilità
(§6.3).

Il drag & drop non è testabile in automatico: è verifica manuale, ed è il
criterio di uscita di M3 (§12).

### 10.4 Guardie architetturali — test veri, non convenzioni

```python
def test_no_file_over_400_lines(): ...
def test_engine_never_imports_ui(): ...
def test_model_layer_has_no_io(): ...
```

Sono i tre test che impediscono al progetto di tornare quello di prima.

---

## 11. Regole di scrittura del codice

Il progetto precedente è fallito per accumulo, non per incapacità. Queste
regole servono a impedire che risucceda.

1. **Nessun file oltre 400 righe.** Verificato in CI.
2. **Nessuna funzione oltre 50 righe.**
3. **Type hints ovunque**, `from __future__ import annotations` in testa.
4. **Nessun import circolare.** Le dipendenze scorrono in una direzione (§3).
5. **Nessun `except: pass`.** Ogni eccezione o si gestisce o si rilancia.
6. **Nessun singleton, nessuno stato globale**, tranne il logger.
7. **Nessun parametro magico non nominato.** `overlap=0.1`, mai `0.1`.
8. **I commenti spiegano il perché, mai il cosa.** Se serve un commento per
   dire cosa fa una riga, va riscritta la riga.
9. **Nessuna dipendenza nuova senza giustificazione scritta** nel commit.
10. **Nessuna feature non presente in questa spec.** Se sembra una buona
    idea, si scrive in fondo al README sotto "Idee" e si va avanti.

---

## 12. Milestone

Ognuno termina con un criterio di uscita verificabile. **Non si passa al
successivo senza aver soddisfatto il precedente.**

### M1 — Il motore

`model/`, `engine/` (incluso `planner.py` e `calibrate.py`),
`export/folder.py`, `cli.py`. Nessuna UI.

> **Uscita:** `stemforge brano.mp3 --stems vocals,drums,bass,other`
> produce quattro WAV corretti; l'invariante di ricostruzione (§10.2)
> passa, anche sul fixture a 48 kHz. **E inoltre:**
> `stemforge brano.mp3 --stems vocals --quality balanced` esegue **una
> sola passata** (verificato dal piano e dal log) con un tempo misurato
> sotto **0.35×** quello dei quattro stem (§6.3), e lo stem risultante
> differisce da quello dell'insieme completo per meno di −25 dBFS RMS
> (§5.1.1). I tempi assoluti vengono misurati sul Mac Intel di
> riferimento e riportati nel README (§5.4) — sono documentazione, non
> criterio di passaggio.

### M2 — App standalone

`worker/`, `ui/`, quattro schermate, packaging PyInstaller x86_64.

> **Uscita:** un `.app` che si apre con doppio click su un Mac Intel
> pulito, senza Python installato, esegue la calibrazione al primo avvio,
> separa un brano e mostra i risultati. Annulla funziona entro 1 s. La
> stima mostrata prima di partire non viene superata (con il margine del
> 15% di §8.2.1).

### M3 — Drag & drop

Trascinamento singolo e multiplo, feedback visivo, rivelazione nel Finder.

> **Uscita — verifica manuale obbligatoria:** con Ableton aperto su un
> progetto reale, si selezionano quattro stem in StemForge e si trascinano
> nell'arrangiamento in un solo gesto. Ableton crea quattro tracce, i file
> sono integri, e partono allineati. Il gesto funziona al **primo** tentativo
> anche se StemForge non ha il fuoco. Questo è il momento in cui il progetto
> diventa davvero utile.

### M4 — Qualità

Backend RoFormer accanto a Demucs, scelto secondo §5.8.

> **Uscita:** RoFormer batte `htdemucs_ft` in un test A/B in cieco su
> voce; l'invariante di ricostruzione regge; il preset resta
> selezionabile; il suo costo è calibrato separatamente e la stima in UI
> resta onesta anche quando dice "ore". La licenza del checkpoint scelto
> è registrata per iscritto (§5.8).

### M5 — Rifinitura

Batch, preview d'ascolto, notarizzazione (con il gate licenze di §9.3).

> **Uscita:** 20 brani in coda senza perdite di memoria e con i modelli
> caricati una volta sola (§6.1); app notarizzata che si apre su un Mac
> di terze parti senza avvisi di sicurezza.

### M6 — Stem derivati

`engine/drumsplit.py`, `vocalsplit.py`, `dereverb.py`, blocchi a
fisarmonica nell'UI (§8.2). Modelli scelti secondo la procedura di §5.8.

Ordine di implementazione, dal più redditizio al meno:

1. **Split batteria** — il derivato con la resa migliore, e quello che apre
   più possibilità in fase di campionamento.
2. **De-riverbero voce** — trasformazione singola, nessun grafo di
   dipendenze da gestire, effetto immediatamente percepibile.
3. **Lead / cori** — il più fragile dei tre.

> **Uscita:** kick e snare estratti da un brano reale sono utilizzabili
> singolarmente senza artefatti udibili; l'invariante di ricostruzione
> regge a due livelli (§10.2); il pianificatore risolve correttamente tutte
> le combinazioni coperte dai test di §10.3; le passate di 2° stadio sono
> calibrate e la stima resta onesta.

**Se uno dei tre non raggiunge una qualità utilizzabile, non si spedisce.**
Uno stem derivato mediocre è peggio della sua assenza: l'utente lo prova
una volta, non funziona, e smette di fidarsi anche del resto.

---

## 13. Cose che questa spec non promette

**13.1 — Niente separazione in tempo reale.** Mai, con questa
architettura. Vedi §7.0.

**13.2 — Il C++ non è in questa spec.** L'esportazione dei modelli fuori
da torch (CoreML o ONNX) ridurrebbe il bundle da ~1 GB a ~200 MB e
l'avvio da cinque secondi a uno. Ma su Mac Intel non c'è Neural Engine:
CoreML girerebbe comunque su CPU, quindi il guadagno sarebbe di peso e
avvio, non di velocità di calcolo. È un lavoro autonomo, da valutare
**dopo** M5, non prima. Farlo adesso rallenterebbe tutto senza migliorare
nulla di percepibile.

**13.3 — Windows e Linux non sono target della v1.** Il codice resta
portabile (nessuna API macOS fuori da `ui/` e `packaging/`) — ed è già
esercitato su Windows ogni giorno, perché lo sviluppo avviene lì (D6) —
ma packaging, firma e test di consegna sono solo macOS. Aggiungere
Windows come *target* dopo M5 è ragionevole; farlo prima raddoppia il
lavoro di packaging a metà progetto.
