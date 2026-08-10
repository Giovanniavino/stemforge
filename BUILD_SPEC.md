# StemForge — Specifica di costruzione

> Documento unico e autosufficiente. Chi implementa non deve chiedere nulla:
> ogni decisione è già presa qui, con la motivazione accanto.

Versione spec: 2.1 · Target: macOS 12+ (Apple Silicon nativo) · Data: 2026-08-10

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
| O4 | Qualità: nessuna regressione udibile rispetto a Demucs `htdemucs_ft` | §11 |
| O5 | Velocità: brano di 4 min in < 60 s su M1 in preset `balanced` | §11 |
| O6 | Non blocca mai: UI reattiva e annullabile durante l'elaborazione | §8.4 |
| O7 | **Il tempo scala con quanto si chiede**: un solo stem costa una frazione di tutti | §5.3 |

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
dentro le primitive tensoriali, che sono già C++/Metal compilato. Il
linguaggio dell'involucro è irrilevante per la qualità e quasi irrilevante
per la velocità.

Java è escluso senza appello: nessun ecosistema ML audio, e la JVM è un
peso morto in un'app che deve muovere centinaia di MB di float.

C++ tornerà utile solo in §13.2, se un giorno si vorrà eliminare la
dipendenza da torch esportando in CoreML. Non è nello scope della v1.

### D2 — Processo separato per l'inferenza

L'UI e il motore girano in **due processi**, non due thread.

Motivo: torch su MPS può bloccarsi o esaurire memoria in modi che non si
recuperano nello stesso processo, e il GIL rende comunque il threading
inutile qui. Un processo figlio si può **uccidere davvero** quando l'utente
preme Annulla — con un thread non si può.

Comunicazione: `multiprocessing` con una `Queue` per i messaggi di
avanzamento. Nessun socket, nessun HTTP, nessun server locale.

### D3 — UI in PySide6 (Qt), non Electron né web

Un solo linguaggio in tutto il progetto. PyInstaller produce un `.app`
nativo. Electron aggiungerebbe 150 MB e un secondo runtime per disegnare
quattro schermate.

**Vincolo anti-degenerazione:** il progetto precedente è morto con un
controller da 3107 righe. Regola dura, verificata in CI (§10.4):
**nessun file supera le 400 righe.** Se cresce, si spacca.

### D4 — Backend di separazione intercambiabili

Il campo si muove in fretta: Demucs oggi, RoFormer domani, altro fra un
anno. Il motore espone un contratto stabile (§5.2) e ogni famiglia di
modelli è un modulo isolato. Cambiare modello non deve toccare UI, export
o data model.

### D5 — L'output è una cartella di WAV più un manifest

Nessun formato proprietario, nessun database, nessuna libreria interna.
Una cartella di file che l'utente può aprire, spostare, trascinare e
cancellare con il Finder. Il `manifest.json` accanto serve all'app per
ripopolare la schermata risultato senza ricalcolare niente.

---

## 2. Stack — versioni esatte

| Componente | Versione | Nota |
|---|---|---|
| Python | **3.12.x** | 3.13+ non è supportato da torch. 3.11 accettabile. |
| PyTorch | >= 2.4 | MPS stabile su Apple Silicon |
| torchaudio | pari a torch | |
| demucs | >= 4.0.1 | backend base |
| soundfile | >= 0.12 | I/O, richiede libsndfile |
| PySide6 | >= 6.7 | UI |
| numpy | >= 1.26, < 3 | |
| pytest | >= 8 | |
| PyInstaller | >= 6.6 | packaging `.app` |

Fissare tutto in `requirements.lock` con hash. `pyproject.toml` per i range.

---

## 3. Struttura del repository

Da creare esattamente così. I conteggi righe sono tetti, non obiettivi.

```
stemforge/
├── BUILD_SPEC.md                  questo file
├── README.md                      uso, 1 pagina
├── pyproject.toml
├── requirements.lock
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
│   │   ├── device.py              CUDA / MPS / CPU          (~70)
│   │   └── audio_io.py            load, resample, write     (~130)
│   │
│   ├── worker/                    — processo figlio
│   │   ├── protocol.py            messaggi UI <-> worker    (~90)
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
    ├── stemforge.spec             PyInstaller
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

Il grafo delle dipendenze è ciò che permette al pianificatore (§5.6) di
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
    device: str               # "auto" | "cpu" | "cuda" | "mps"
    dereverb_vocals: bool = False   # §5.2.3, opzione non stem
```

Immutabile. Serializzabile in JSON (attraversa il confine fra processi).

### 4.3 `manifest.json` — contratto stabile

Scritto accanto agli stem.

```json
{
  "schema": 1,
  "source": { "name": "brano.mp3", "sha1": "…", "duration_s": 214.7 },
  "audio":  { "samplerate": 44100, "channels": 2, "bit_depth": 24 },
  "engine": { "backend": "demucs", "model": "htdemucs_ft",
              "quality": "balanced", "version": "0.1.0" },
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
specializzati** (uno per sorgente) che vengono eseguiti tutti e poi mediati.
È da lì che viene la sua qualità superiore, ed è da lì che viene il suo
costo: quattro inferenze complete.

**Se l'utente chiede un solo stem base, si esegue soltanto il sotto-modello
specializzato in quella sorgente.** Chi vuole solo la voce paga circa un
quarto del tempo, e la ottiene alla stessa qualità — perché il sotto-modello
della voce è esattamente ciò che rende `htdemucs_ft` buono sulla voce.

Regola di attivazione:

| Stem base richiesti | Esecuzione |
|---|---|
| 1 (più eventuale `other`/`instrumental`) | **solo** il sotto-modello corrispondente |
| 2 o 3 | i sotto-modelli corrispondenti |
| 4 | insieme completo, come oggi |

Il complemento si ricava per sottrazione: `other = mix − stem_richiesti`.
La sottrazione è esatta, quindi l'invariante di §10.2 regge per costruzione
— anzi, regge *meglio* del caso completo.

**Verifica obbligatoria** (`tests/integration/test_single_source.py`): lo
stem prodotto dal solo sotto-modello va confrontato con quello prodotto
dall'insieme completo. Differenza attesa sotto −25 dBFS RMS. Se emergesse
una differenza udibile, l'ottimizzazione va limitata al preset `fast` e
`balanced`, lasciando `best` sempre completo. Non va rimossa: il guadagno
è troppo grande.

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

Il pianificatore riceve gli stem richiesti e produce un piano di esecuzione:

1. **Chiusura delle dipendenze.** Per ogni derivato richiesto, aggiungere il
   suo `derives_from`. Chi chiede `kick` fa calcolare `drums` anche senza
   averlo spuntato — ma `drums.wav` viene scritto solo se richiesto
   esplicitamente.
2. **Scelta del modello di 1° stadio** (§5.1): `6s` solo se servono chitarra
   o piano.
3. **Applicazione di §5.1.1** se i base sono tre o meno e il modello è `ft`.
4. **Elenco delle passate di 2° stadio**, una per stem base coinvolto.
5. **Stima del tempo** = somma dei costi di ogni passata, dove ogni passata
   ha un costo misurato e tabellato per device e preset.

Il piano è un oggetto ispezionabile e **testabile senza torch**: dato un
insieme di stem richiesti, produce un elenco di passate. È il pezzo di
logica con più casi limite di tutto il progetto e va coperto da test
unitari esaustivi, non da test di integrazione lenti.

### 5.4 Tempi risultanti — MacBook Air M1, brano 4 min, `balanced`

| Richiesta | Passate | Tempo |
|---|---|---|
| solo `vocals` | 1 sotto-modello | **~18 s** |
| `vocals` + `instrumental` | 1 sotto-modello + sottrazione | ~18 s |
| `vocals` + `drums` | 2 sotto-modelli | ~32 s |
| i 4 base | insieme completo | ~60 s |
| i 6 base (con chitarra/piano) | `6s`, passata singola | ~45 s |
| 4 base + split batteria | completo + 1 | ~70 s |
| 4 base + split batteria + lead/cori + de-riverbero | completo + 3 | **~85 s** |

Il rapporto fra il minimo e il massimo è quasi **1 a 5**. È l'obiettivo O7,
ed è ciò che rende l'app usabile sia per un lavoro veloce che per una resa
completa.

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

Due punti non negoziabili:

- `should_cancel` va consultato **fra un chunk e l'altro**, non solo a fine
  brano. Annullare deve avere effetto entro un secondo.
- `on_progress` riceve 0.0–1.0 monotòno crescente. Mai all'indietro.

### 5.6 Preset qualità

```python
@dataclass(frozen=True)
class Quality:
    overlap: float
    shifts: int
    half: bool
    segment_s: float | None
```

| Preset | overlap | shifts | fp16 | segment | Uso |
|---|---|---|---|---|---|
| `fast` | 0.05 | 0 | sì | 7.8 | anteprima, batch |
| `balanced` | 0.10 | 0 | sì | 7.8 | **default** |
| `best` | 0.25 | 2 | no | 7.8 | consegna finale |

Perché questi numeri:

- **`shifts` è la leva peggiore che esista.** Ogni shift è un'inferenza
  completa in più per una frazione di dB. Default 0. Sta solo in `best`.
- **`overlap` oltre 0.25 non serve a niente**, e sotto 0.05 iniziano a
  sentirsi le giunzioni. Il costo è lineare.
- **fp16 solo su GPU/MPS.** Su CPU è emulato e più lento: forzarlo a
  `False` quando `device == "cpu"`, ignorando il preset.

### 5.7 I/O audio — regole

1. Decodifica sempre a **float32**, mai int.
2. I modelli girano a **44100 Hz**. Se la sorgente ha un altro sample rate,
   resample in ingresso e **resample indietro in uscita**: l'utente deve
   riavere il suo sample rate originale, o gli stem non si allineeranno una
   volta trascinati nel progetto.
3. Mono in ingresso → duplicato su due canali per il modello → **riscritto
   mono** in uscita.
4. Scrittura a **24 bit PCM** di default. Mai 16 bit: gli stem hanno
   headroom bassa e il quantization noise si sente quando li rialzi.
5. **Nessuna normalizzazione, nessun limiting, nessun fade.** Se la somma
   degli stem non ricostruisce il mix (entro l'errore del modello), è un
   bug. La DAW è il posto dove si mixa.
6. File > 15 minuti: elaborare a blocchi con crossfade, per non esaurire la
   RAM. Limite duro 30 minuti, oltre il quale si rifiuta con messaggio
   chiaro.

---

## 6. Performance

### 6.1 Obiettivi misurabili — MacBook Air M1, brano stereo 4 min 44.1 kHz

| Configurazione | Tetto |
|---|---|
| `balanced`, htdemucs_ft, MPS | **60 s** |
| `fast`, htdemucs, MPS | 25 s |
| `best`, htdemucs_ft, MPS | 240 s |
| `balanced`, CPU (fallback) | 300 s |

Il benchmark è in `tests/integration/test_perf.py`, salta se non su Apple
Silicon, e **fallisce** se un tetto viene superato del 25%.

### 6.2 Cosa fare, in ordine di resa

1. **MPS invece di CPU** — 5–8x. La singola cosa che conta di più.
2. **fp16** — ~1.8x, nessuna perdita udibile.
3. **`shifts=0`** — evita di moltiplicare per 3 il tempo.
4. **`overlap` 0.25 → 0.10** — ~1.6x.
5. **Caricare il modello una volta sola** in batch. In un job da 20 file il
   caricamento ripetuto è metà del tempo totale.
6. **Decodifica del file successivo mentre il corrente è in inferenza** —
   utile solo su batch, ~5%. Farlo per ultimo.

### 6.3 Cosa NON fare

- Non mettere `torch.compile`: su MPS costa più in compilazione di quanto
  restituisca su un brano solo.
- Non aumentare `segment` per "andare più veloce": alza la RAM in modo
  quadratico e su 8 GB fa swappare, che è molto peggio.
- Non parallelizzare due brani sulla stessa GPU: si contendono la memoria e
  vanno entrambi più piano della somma in serie.

---

## 7. Consegna alla DAW

### 7.0 Perché non un plugin

Un plugin gira nel thread audio della DAW, con un budget di pochi
millisecondi per buffer e il divieto assoluto di allocare memoria. La
separazione neurale richiede **decine di secondi** e gigabyte di RAM. Non è
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

**In fondo** due soli controlli: **preset qualità** e **formato**.

#### 8.2.1 La stima del tempo

Sempre visibile, in basso, aggiornata dal vivo a ogni spunta. Viene dal
pianificatore (§5.3), non da una formula approssimata nell'UI: è la somma
reale delle passate che verranno eseguite.

- **Deve scendere quando si toglie roba**, e visibilmente. È il feedback che
  insegna all'utente che chiedere meno costa meno — senza quel feedback,
  l'ottimizzazione di §5.1.1 esiste ma nessuno la sfrutta.
- Va **sovrastimata del 15%**: finire prima del previsto è un piacere, dopo
  è un difetto.
- Accanto, il numero di passate in chiaro: *"~18 s · 1 passata"*.

### 8.3 Schermata 3 — Avanzamento

- Barra 0–100% con la fase corrente in parole: *"Separazione — passata 2
  di 3"*, *"Dettaglio batteria"*, *"Scrittura stem"*.
- Con più passate, l'avanzamento globale è la **somma pesata** dei costi
  stimati di ciascuna, non la media semplice: le passate di 2° stadio sono
  molto più corte della prima e una barra che le trattasse alla pari
  sembrerebbe bloccata all'inizio e poi scattante alla fine.
- Tempo rimanente, aggiornato ogni 2 s, con media mobile per non farlo
  saltellare.
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

- **`target_arch = "arm64"`.** Universal2 richiede una toolchain doppia per
  torch e non ne vale la pena: l'utente è su Apple Silicon.
- Escludere `matplotlib`, `tkinter`, `IPython`, `pytest` e ogni backend Qt
  non usato. Senza esclusioni il bundle passa 1 GB.
- `.app` con `Info.plist` che dichiara i tipi di file audio in
  `CFBundleDocumentTypes`, così "Apri con" funziona dal Finder.

### 9.2 I pesi dei modelli

**Non impacchettare i pesi nell'app** (htdemucs_ft è ~700 MB in quattro
file). Scaricarli al primo avvio, con barra di avanzamento e destinazione
`~/Library/Application Support/StemForge/models/`.

Verificare **SHA-256** di ogni file scaricato contro una lista fissata nel
codice. Un peso corrotto a metà download deve essere riconosciuto e
riscaricato, non caricato.

Se non c'è rete al primo avvio: messaggio esplicito che serve la
connessione **una sola volta**, poi l'app è offline per sempre.

### 9.3 Firma

Per uso personale basta `codesign --force --deep --sign -` (ad-hoc), poi
click destro → Apri la prima volta.

Per distribuire a terzi serve un Apple Developer Program (99 $/anno):
`codesign` con Developer ID, hardened runtime, `entitlements.plist` con
`com.apple.security.cs.allow-unsigned-executable-memory` (torch ne ha
bisogno), poi `notarytool submit --wait` e `stapler staple`.
`packaging/notarize.sh` va scritto ma **non** invocato dalla build di default.

### 9.4 Primo avvio

Sequenza: controllo pesi → download se mancano → finestra principale.
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
| RAM esaurita su MPS | ricade su CPU **automaticamente**, avvisa, continua |
| Disco pieno | controlla lo spazio **prima** di iniziare, stima 4× la durata |
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
trascinato nel progetto), e sample rate identico.

L'invariante vale **a ogni livello dell'albero**: se sono stati prodotti
kick, snare, toms, hi-hat e cymbals, la loro somma più il residuo deve
ricostruire `drums`. Unica eccezione ammessa in tutta la spec: il
de-riverbero (§5.2.3), che va testato sulla versione `_wet`.

### 10.3 Unitari e integrazione

Unitari senza torch, veloci: `model/`, `manifest`, `device`, parsing CLI,
naming e collisioni di cartella. Tempo totale **< 5 secondi**.

**Il pianificatore (§5.3) va coperto in modo esaustivo**, ed è il test
unitario più importante del progetto perché è dove si annidano i casi
limite: chiedere `kick` senza `drums`; chiedere `lead_vocals` con
`dereverb` attivo; chiedere solo `instrumental`; chiedere un derivato di
`drums` e uno di `vocals` insieme; chiedere tutto. Per ognuno si verifica
il modello di 1° stadio scelto, l'elenco esatto delle passate, e quali file
finiscono su disco. Gira senza torch, in millisecondi.

Integrazione: pipeline completa con backend finto (< 10 s); pipeline con
Demucs reale marcata `@pytest.mark.slow`; annullamento che uccide il
processo entro 1 s senza lasciare parziali.

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

`model/`, `engine/` (incluso `planner.py`), `export/folder.py`, `cli.py`.
Nessuna UI.

> **Uscita:** `stemforge brano.mp3 --stems vocals,drums,bass,other` produce
> quattro WAV corretti; l'invariante di ricostruzione (§10.2) passa; il
> tetto di 60 s (§6.1) è rispettato. **E inoltre:**
> `stemforge brano.mp3 --stems vocals` finisce in **meno di 25 s**,
> dimostrando che §5.1.1 funziona, con lo stem indistinguibile da quello
> prodotto dall'insieme completo.

### M2 — App standalone

`worker/`, `ui/`, quattro schermate, packaging PyInstaller.

> **Uscita:** un `.app` che si apre con doppio click su un Mac pulito, senza
> Python installato, separa un brano e mostra i risultati. Annulla funziona
> entro 1 s.

### M3 — Drag & drop

Trascinamento singolo e multiplo, feedback visivo, rivelazione nel Finder.

> **Uscita — verifica manuale obbligatoria:** con Ableton aperto su un
> progetto reale, si selezionano quattro stem in StemForge e si trascinano
> nell'arrangiamento in un solo gesto. Ableton crea quattro tracce, i file
> sono integri, e partono allineati. Il gesto funziona al **primo** tentativo
> anche se StemForge non ha il fuoco. Questo è il momento in cui il progetto
> diventa davvero utile.

### M4 — Qualità

Backend RoFormer accanto a Demucs.

> **Uscita:** RoFormer batte `htdemucs_ft` in un test A/B in cieco su voce;
> l'invariante di ricostruzione regge; il preset resta selezionabile.

### M5 — Rifinitura

Batch, preview d'ascolto, notarizzazione.

> **Uscita:** 20 brani in coda senza perdite di memoria; app notarizzata
> che si apre su un Mac di terze parti senza avvisi di sicurezza.

### M6 — Stem derivati

`engine/drumsplit.py`, `vocalsplit.py`, `dereverb.py`, blocchi a
fisarmonica nell'UI (§8.2).

Ordine di implementazione, dal più redditizio al meno:

1. **Split batteria** — il derivato con la resa migliore, e quello che apre
   più possibilità in fase di campionamento.
2. **De-riverbero voce** — trasformazione singola, nessun grafo di
   dipendenze da gestire, effetto immediatamente percepibile.
3. **Lead / cori** — il più fragile dei tre.

> **Uscita:** kick e snare estratti da un brano reale sono utilizzabili
> singolarmente senza artefatti udibili; l'invariante di ricostruzione
> regge a due livelli (§10.2); il pianificatore risolve correttamente tutte
> le combinazioni coperte dai test di §10.3; il tempo dichiarato in §5.4
> per la richiesta massima è rispettato.

**Se uno dei tre non raggiunge una qualità utilizzabile, non si spedisce.**
Uno stem derivato mediocre è peggio della sua assenza: l'utente lo prova
una volta, non funziona, e smette di fidarsi anche del resto.

---

## 13. Cose che questa spec non promette

**13.1 — Niente separazione in tempo reale.** Mai, con questa
architettura. Vedi §7.0.

**13.2 — Il C++ non è in questa spec.** Il momento in cui avrà senso è
quando si vorrà eliminare torch dal bundle esportando i modelli in CoreML:
l'app scenderebbe da ~1 GB a ~200 MB e partirebbe in un secondo invece che
in cinque. È un lavoro autonomo, da fare **dopo** M5, non prima. Farlo
adesso rallenterebbe tutto senza migliorare nulla di percepibile.

**13.3 — Windows e Linux non sono target della v1.** Il codice resta
portabile (nessuna API macOS fuori da `ui/` e `packaging/`), ma packaging,
firma e test sono solo macOS. Aggiungere Windows dopo M5 è ragionevole;
farlo prima raddoppia il lavoro di packaging a metà progetto.
