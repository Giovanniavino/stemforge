# StemForge — Specifica di costruzione

> Documento unico e autosufficiente. Chi implementa non deve chiedere nulla:
> ogni decisione è già presa qui, con la motivazione accanto.
> Dove una cosa **non** è realizzabile, è scritto esplicitamente.

Versione spec: 1.0 · Target: macOS 12+ (Apple Silicon nativo) · Data: 2026-08-10

---

## 0. Cos'è e cosa non è

**StemForge è un'applicazione desktop standalone che prende un file audio,
lo separa in tracce strumentali scelte dall'utente, e produce un progetto
già pronto da aprire nella sua DAW.**

L'utente fa tre cose: trascina un brano, spunta gli strumenti che vuole,
preme Separa. Ottiene una cartella di stem **e** un file `.als` che, aperto,
è una sessione Ableton con ogni stem già sulla sua traccia, in tempo, al
tempo giusto.

### Obiettivi

| # | Obiettivo | Verificabile come |
|---|---|---|
| O1 | Separazione multi-strumento con scelta dell'utente | §5 |
| O2 | Progetto DAW generato, non solo file sciolti | §7 |
| O3 | App standalone, doppio click, zero terminale, zero Python da installare | §9 |
| O4 | Qualità: nessuna regressione udibile rispetto a Demucs `htdemucs_ft` | §12 |
| O5 | Velocità: brano di 4 min in < 60 s su M1 in preset `balanced` | §12 |
| O6 | Non blocca mai: UI reattiva e annullabile durante l'elaborazione | §8.4 |

### Non-obiettivi — da rifiutare se emergono in corso d'opera

- **Non è un plugin VST/AU.** Niente processing in tempo reale. Vedi §7.0
  per il perché questa è la scelta giusta e non una rinuncia.
- **Niente slicing, pad, sampler, sequencer, effetti, mixer.** Il vecchio
  progetto è morto di questo. Se una feature non serve a separare o a
  consegnare alla DAW, non entra.
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

C++ tornerà utile solo in §14.3, se un giorno si vorrà eliminare la
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
controller da 3107 righe. Regola dura, verificata in CI (§11.4):
**nessun file supera le 400 righe.** Se cresce, si spacca.

### D4 — Backend di separazione intercambiabili

Il campo si muove in fretta: Demucs oggi, RoFormer domani, altro fra un
anno. Il motore espone un contratto stabile (§5.2) e ogni famiglia di
modelli è un modulo isolato. Cambiare modello non deve toccare UI, export,
o data model.

### D5 — L'output canonico è una cartella, il progetto DAW è derivato

Il risultato primario è sempre una cartella di WAV più un `manifest.json`.
I file di progetto (`.als`, `.RPP`, AAF) sono **generati da quel manifest**,
mai il contrario. Così un formato DAW rotto non fa perdere il lavoro di
separazione, e aggiungere una DAW è scrivere un solo writer.

### D6 — Il `.als` si genera da template, non da zero

Lo schema XML di Ableton non è documentato e cambia tra versioni maggiori.
Scriverlo a mano da zero è garanzia di rotture. Vedi §7.2 per il metodo.

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
| aaf2 | >= 1.7 | export AAF (§7.4) |
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
│   │   ├── stem.py                StemKind, StemSpec        (~90)
│   │   ├── job.py                 SeparationJob, JobResult  (~90)
│   │   └── manifest.py            Manifest r/w JSON         (~120)
│   │
│   ├── engine/                    — separazione
│   │   ├── contract.py            Backend Protocol, Quality (~90)
│   │   ├── registry.py            nome -> backend           (~60)
│   │   ├── demucs4.py             backend Demucs v4         (~140)
│   │   ├── roformer.py            backend RoFormer (M4)     (~180)
│   │   ├── cascade.py             separazione a 2 stadi     (~180)
│   │   ├── device.py              CUDA / MPS / CPU          (~70)
│   │   └── audio_io.py            load, resample, write     (~130)
│   │
│   ├── worker/                    — processo figlio
│   │   ├── protocol.py            messaggi UI <-> worker    (~90)
│   │   └── runner.py              entry point del figlio    (~150)
│   │
│   ├── export/                    — consegna alla DAW
│   │   ├── folder.py              WAV + manifest            (~110)
│   │   ├── ableton.py             .als da template          (~260)
│   │   ├── reaper.py              .RPP                      (~120)
│   │   ├── aaf_export.py          AAF                       (~140)
│   │   └── templates/
│   │       └── live12_empty.als   template versionato (§7.2)
│   │
│   ├── ui/                        — Qt, nessuna logica
│   │   ├── app.py                 bootstrap                 (~90)
│   │   ├── main_window.py         shell + routing           (~200)
│   │   ├── drop_zone.py           schermata 1               (~150)
│   │   ├── stem_picker.py         schermata 2               (~220)
│   │   ├── progress_view.py       schermata 3               (~160)
│   │   ├── result_view.py         schermata 4               (~180)
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

```python
class StemKind(StrEnum):
    VOCALS      = "vocals"
    BACKING     = "backing_vocals"
    DRUMS       = "drums"
    BASS        = "bass"
    GUITAR      = "guitar"
    PIANO       = "piano"
    STRINGS     = "strings"
    WINDS       = "winds"
    SYNTH       = "synth"
    OTHER       = "other"
```

### 4.2 `StemSpec` — la tabella della verità

Ogni stem dichiara **come** si ottiene e **quanto** ci si può fidare.
Questa tabella è ciò che permette all'UI di essere onesta con l'utente
invece di promettere risultati uguali per tutto.

| Stem | Come si ottiene | Affidabilità | Mostrato come |
|---|---|---|---|
| `vocals` | modello primario | **alta** | stabile |
| `drums` | modello primario | **alta** | stabile |
| `bass` | modello primario | **alta** | stabile |
| `guitar` | Demucs 6s / cascata | media | "sperimentale" |
| `piano` | Demucs 6s / cascata | media | "sperimentale" |
| `backing_vocals` | 2° stadio su `vocals` | bassa | "sperimentale" |
| `strings` | 2° stadio su `other` | **bassa** | "sperimentale" |
| `winds` | 2° stadio su `other` | **bassa** | "sperimentale" |
| `synth` | 2° stadio su `other` | bassa | "sperimentale" |
| `other` | residuo | — | sempre disponibile |

`reliability` è un campo del `StemSpec`, non un commento. L'UI legge quello
per decidere il badge (§8.2). **Nessun stem sperimentale viene presentato
come se fosse alla pari con la voce.**

### 4.3 `SeparationJob`

```python
@dataclass(frozen=True)
class SeparationJob:
    source: Path
    wanted: tuple[StemKind, ...]
    quality: str            # "fast" | "balanced" | "best"
    out_dir: Path
    formats: tuple[str, ...]  # "wav", "flac"
    daw_exports: tuple[str, ...]  # "ableton", "reaper", "aaf"
    device: str             # "auto" | "cpu" | "cuda" | "mps"
```

Immutabile. Serializzabile in JSON (attraversa il confine fra processi).

### 4.4 `manifest.json` — contratto stabile

Scritto accanto agli stem. È l'input di **tutti** gli export DAW.

```json
{
  "schema": 1,
  "source": { "name": "brano.mp3", "sha1": "…", "duration_s": 214.7 },
  "audio":  { "samplerate": 44100, "channels": 2, "bit_depth": 24 },
  "tempo":  { "bpm": 128.0, "confidence": 0.91, "detected": true },
  "engine": { "backend": "demucs", "model": "htdemucs_ft",
              "quality": "balanced", "version": "0.1.0" },
  "stems": [
    { "kind": "vocals", "file": "vocals.wav",
      "reliability": "high", "peak_dbfs": -1.2, "rms_dbfs": -18.4 }
  ],
  "created_utc": "2026-08-10T14:22:31Z"
}
```

`schema` va incrementato a ogni cambio incompatibile; i reader rifiutano
uno schema che non conoscono con un errore chiaro.

---

## 5. Il motore di separazione

### 5.1 Come si ottengono davvero più di 4 strumenti

**Va detto senza giri di parole: non esiste oggi un modello aperto che
separi archi, fiati e synth con la stessa pulizia con cui separa la voce.**
La voce è il caso su cui è concentrata quasi tutta la ricerca; il resto è
molto più indietro. Una specifica che promettesse dieci stem tutti perfetti
sarebbe una specifica falsa.

Quello che si può fare bene è una **cascata a due stadi**:

```
                       ┌─ vocals   ── alta affidabilità
                       ├─ drums    ── alta
   MIX ──[ stadio 1 ]──┼─ bass     ── alta
                       ├─ guitar   ── media
                       ├─ piano    ── media
                       └─ other ──[ stadio 2 ]──┬─ strings  ── bassa
                                                ├─ winds    ── bassa
                                                ├─ synth    ── bassa
                                                └─ other    ── residuo
```

**Stadio 1** — Demucs `htdemucs_6s` se l'utente chiede chitarra o piano,
altrimenti `htdemucs_ft` (più pulito sui quattro classici).

**Stadio 2** — gira **solo se** l'utente ha chiesto uno stem di secondo
livello, e opera **solo** sul residuo `other`. In M1–M3 non esiste ancora:
lo stadio 2 restituisce `other` intatto e l'UI mostra gli stem di secondo
livello come non ancora disponibili. Si attiva in M4 (§12) con un modello
specializzato. **Non inventare un separatore di archi con DSP a mano:
darebbe un risultato pessimo e screditerebbe l'app.**

**Invariante della cascata, sempre valido:**
la somma di tutti gli stem prodotti deve ricostruire il mix originale entro
−40 dBFS di errore. Se il secondo stadio produce N stem da `other`, il loro
residuo rientra in `other`. Test obbligatorio in §11.2.

### 5.2 Contratto `Backend`

```python
class Backend(Protocol):
    name: str
    provides: frozenset[StemKind]     # cosa sa produrre
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

### 5.3 Preset qualità

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

### 5.4 I/O audio — regole

1. Decodifica sempre a **float32**, mai int.
2. I modelli girano a **44100 Hz**. Se la sorgente ha un altro sample rate,
   resample in ingresso e **resample indietro in uscita**: l'utente deve
   riavere il suo sample rate originale, o gli stem non si allineeranno al
   progetto della DAW.
3. Mono in ingresso → duplicato su due canali per il modello → **riscritto
   mono** in uscita.
4. Scrittura a **24 bit PCM** di default. Mai 16 bit: gli stem hanno
   headroom bassa e il quantization noise si sente quando li rialzi.
5. **Nessuna normalizzazione, nessun limiting, nessun fade.** Se la somma
   degli stem non ricostruisce il mix bit per bit (entro l'errore del
   modello), è un bug. La DAW è il posto dove si mixa.
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

## 7. Integrazione DAW — il capitolo centrale

### 7.0 Perché non un VST, e perché è meglio così

Un plugin gira nel thread audio della DAW, con un budget di pochi
millisecondi per buffer e il divieto assoluto di allocare memoria. La
separazione neurale richiede **decine di secondi** e gigabyte di RAM. Non è
una limitazione dell'implementazione: è incompatibilità di natura. Ogni
prodotto commerciale che offre separazione "in un plugin" in realtà fa
esattamente quello che facciamo qui — elabora offline e consegna file.

Consegnare un **progetto DAW già montato** è migliore di un plugin sotto
ogni aspetto che conta: nessuna installazione, nessun problema di
compatibilità di versione o di formato, nessun crash che porta giù la
sessione dell'utente, e funziona con **qualunque** DAW invece che con
quelle che ospitano quel formato di plugin.

### 7.1 Livelli di integrazione

| Livello | Meccanismo | DAW coperte |
|---|---|---|
| L1 | cartella WAV + naming coerente | tutte |
| L2 | drag & drop dall'app alla DAW | tutte |
| L3 | **`.als` generato** | **Ableton Live** |
| L4 | `.RPP` generato | Reaper |
| L5 | AAF | Pro Tools, Cubase, Logic, Studio One |

L3 è la priorità: è la DAW dell'utente ed è il livello con la resa più alta.

### 7.2 Ableton `.als` — metodo esatto

**Cos'è.** Un `.als` è un file **XML compresso con gzip**. Si apre con
`gzip.open(path, "rt", encoding="utf-8")` e si ottiene XML leggibile.

**Perché da template e non da zero.** Lo schema non è documentato da
Ableton, contiene centinaia di elementi obbligatori con valori di default
impliciti, e cambia tra versioni maggiori (Live 10 / 11 / 12). Generarlo da
zero significa romperlo a ogni aggiornamento di Live.

**Procedura di implementazione — da seguire in quest'ordine:**

1. **Ottenere il template.** In Live: nuovo Set vuoto, cancellare tutte le
   tracce, salvare come `live12_empty.als`. Metterlo in
   `export/templates/`. **Questo file va prodotto dalla versione di Live
   dell'utente** ed è l'unico input esterno richiesto da questa spec.

2. **Studiare la struttura** decomprimendo il template e isolando:
   - `<Ableton MinorVersion=… Creator=…>` — versione dello schema
   - `<LiveSet>/<Tracks>` — il contenitore da popolare
   - un `<AudioTrack>` completo, da usare come stampo per ogni stem
   - `<MasterTrack>/…/<Tempo>/<Manual Value="…"/>` — il tempo

3. **Costruire il Set:**
   - impostare il tempo dal `manifest.tempo.bpm`; se `detected` è `false`,
     lasciare 120 e non mentire all'utente
   - per ogni stem: clonare lo stampo `<AudioTrack>`, e impostare
     - `Name/EffectiveName` = nome dello stem in maiuscolo (`VOCALS`)
     - `Color` = indice colore da §7.3
     - una `<AudioClip>` che parte a `CurrentStart = 0` e dura tutto il file
     - `SampleRef/FileRef` con percorso **relativo** (vedi punto 5)
     - `Freeze`, `Solo`, `Mute` a `false`; volume a **0 dB**, pan al centro
   - **Ogni `Id` deve essere unico** in tutto il documento. Tenere un
     contatore monotòno e non riusare mai un Id.

4. **Scrivere** con `gzip.open(..., "wt", encoding="utf-8")` preservando la
   dichiarazione XML del template.

5. **Layout su disco — non negoziabile.** Live risolve i sample per
   percorso relativo alla posizione del Set:

   ```
   Brano/
     Brano.als
     Samples/Imported/
       vocals.wav
       drums.wav
   ```

   Percorsi assoluti nel `.als` rendono il progetto non spostabile e non
   condivisibile. **Usare sempre relativi**, con il Set nella cartella
   padre di `Samples/Imported/`.

6. **Verifica automatica** (`tests/unit/test_ableton_roundtrip.py`):
   rileggere il `.als` prodotto, verificare che sia gzip valido, che l'XML
   faccia il parse, che il numero di `<AudioTrack>` corrisponda al numero di
   stem, che ogni percorso sample esista su disco, e che gli `Id` siano
   tutti distinti. Questo test **non** dimostra che Live lo apra: quella
   verifica è manuale ed è un criterio di uscita del milestone M3 (§12).

7. **Fallimento controllato.** Se il template manca, è di una versione non
   riconosciuta, o il writer solleva un'eccezione: **l'export `.als` fallisce
   da solo**, con un messaggio che dice all'utente che gli stem sono comunque
   salvati e dove. Non deve mai far fallire il job di separazione. Vale
   D5: gli stem sono il risultato, il progetto è un di più.

### 7.3 Colori delle tracce

Coerenti fra `.als` e UI, così l'utente riconosce le tracce a colpo d'occhio.

| Stem | Colore |
|---|---|
| `vocals` | rosso |
| `drums` | arancio |
| `bass` | giallo |
| `guitar` | verde |
| `piano` | azzurro |
| `strings` | viola |
| `winds` | rosa |
| `synth` | blu |
| `other` | grigio |

Gli indici numerici della palette di Live vanno letti dal template, non
indovinati.

### 7.4 Reaper e AAF

**Reaper `.RPP`** — testo puro, nessuna compressione, formato semplice e
stabile. Un `<TRACK>` per stem con un `<ITEM>` che punta al WAV. È il writer
più facile di tutti: farlo subito dopo Ableton, costa poco.

**AAF** — via `aaf2`. Copre Pro Tools, Cubase, Logic, Studio One. Un
`MasterMob` per stem, tutti a timecode zero, sample rate dal manifest.
Limite noto da documentare nel README: **l'AAF non trasporta il tempo**, va
impostato a mano nella DAW. Non è un difetto dell'implementazione, è il
formato.

### 7.5 Drag & drop in uscita

Dalla schermata risultato (§8.3) si deve poter trascinare uno stem, o la
selezione multipla, direttamente nell'arrangiamento di Ableton.

In Qt: `QDrag` con `QMimeData.setUrls([QUrl.fromLocalFile(p)])`. È il
meccanismo nativo di macOS e Live lo accetta senza alcuna configurazione.

---

## 8. Interfaccia

Quattro schermate. Nient'altro. Nessun menu di preferenze annidato.

### 8.1 Schermata 1 — Drop

Una zona grande al centro: *"Trascina un brano, o scegli un file."*
Accetta `wav mp3 flac ogg m4a aiff aif`, file multipli, cartelle.
File non audio: rifiutati con messaggio inline, senza dialog modale.

### 8.2 Schermata 2 — Scelta strumenti

Griglia di card, una per `StemKind`. Ogni card: icona, nome, checkbox.

- Gli stem ad affidabilità **alta** sono in cima e preselezionati.
- Gli stem **sperimentali** portano il badge `SPERIMENTALE` e una riga di
  spiegazione onesta: *"La separazione degli archi è ancora imprecisa: parte
  del materiale resterà in Altro."* Questa frase non è pessimismo, è
  gestione delle aspettative — un utente avvisato è soddisfatto, uno
  sorpreso no.
- Gli stem di 2° stadio non ancora implementati sono **disabilitati** con
  la dicitura *"in arrivo"*, non nascosti.
- In fondo, tre controlli e basta: **preset qualità**, **formato**,
  **export DAW** (checkbox Ableton / Reaper / AAF).
- Stima del tempo, calcolata da durata × preset × device, aggiornata dal
  vivo. Va **sovrastimata del 15%**: finire prima del previsto è un piacere,
  dopo è un difetto.

### 8.3 Schermata 3 — Avanzamento

- Barra 0–100% con la fase corrente in parole: *"Separazione — stadio 1 di
  2"*, *"Scrittura stem"*, *"Creazione progetto Ableton"*.
- Tempo rimanente, aggiornato ogni 2 s, con media mobile per non farlo
  saltellare.
- **Pulsante Annulla sempre attivo**, che uccide il processo figlio entro
  1 secondo e ripulisce i file parziali.

### 8.4 Schermata 4 — Risultato

- Elenco stem con durata, picco dBFS, e **preview di ascolto** (play/stop,
  un solo stem alla volta — niente mixer, niente solo/mute: quella è la
  DAW).
- `Apri in Ableton` — apre il `.als` generato con `open` di macOS.
- `Mostra nel Finder`.
- Ogni riga è trascinabile (§7.5).
- Se un export DAW è fallito, riga di avviso non bloccante che dice cosa è
  fallito e conferma che gli stem sono salvi.

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
- Escludere `matplotlib`, `tkinter`, `IPython`, `pytest`, `scipy.spatial` e
  ogni backend Qt non usato. Senza esclusioni il bundle passa 1 GB.
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

## 10. Errori

### 10.1 Regole

1. **Ogni errore mostrato all'utente dice cosa fare.** "Errore di
   separazione" è vietato. "Memoria insufficiente: chiudi altre app o passa
   al preset Veloce" è accettabile.
2. Traceback completo nel log, **mai** in faccia all'utente.
3. Log in `~/Library/Logs/StemForge/stemforge.log`, rotazione a 5 MB × 3.
4. Un file che fallisce in un batch **non ferma gli altri**. Riepilogo alla
   fine.

### 10.2 Casi da gestire nominalmente

| Caso | Comportamento |
|---|---|
| File audio corrotto | salta, messaggio con nome file, continua il batch |
| Formato non supportato | rifiuta al drop, non a metà elaborazione |
| Traccia silenziosa (< −60 dBFS) | scrive comunque, avvisa "quasi silenzioso" |
| RAM esaurita su MPS | ricade su CPU **automaticamente**, avvisa, continua |
| Disco pieno | controlla lo spazio **prima** di iniziare, stima 4× la durata |
| Annulla a metà | uccide il figlio, cancella i parziali, torna alla schermata 2 con le scelte intatte |
| Template `.als` mancante | salta solo quell'export (§7.2 punto 7) |
| Modello non scaricabile | messaggio con causa di rete, riprovabile |
| Brano > 30 min | rifiuta con motivazione esplicita |

---

## 11. Test

### 11.1 Unitari — senza torch, veloci

`model/`, `manifest`, i tre writer DAW, `device`, parsing CLI.
Tempo totale: **< 5 secondi**. Devono girare a ogni salvataggio.

### 11.2 Invariante di ricostruzione — il test più importante

Su un fixture sintetico di 8 secondi (sinusoide + rumore + click, generato
in codice, zero materiale protetto da copyright):

```
somma(stem) - mix_originale  ->  RMS < -40 dBFS
```

Se questo test fallisce, qualcosa nella catena sta normalizzando,
ritardando o scalando l'audio. È la rete di sicurezza contro l'intera
classe di bug più insidiosa.

Verificare anche: **lunghezza in campioni identica** al sorgente (uno
sfasamento di anche un solo campione manda fuori sync il progetto DAW), e
sample rate identico.

### 11.3 Integrazione

- pipeline completa su fixture, backend finto (nessun torch): < 10 s
- pipeline completa con Demucs reale: marcata `@pytest.mark.slow`
- `.als` prodotto → rileggibile, valido, percorsi risolti (§7.2 punto 6)
- annullamento: il processo muore entro 1 s e non lascia file parziali

### 11.4 Guardie architetturali — test veri, non convenzioni

```python
def test_no_file_over_400_lines(): ...
def test_engine_never_imports_ui(): ...
def test_model_layer_has_no_io(): ...
```

Sono i tre test che impediscono al progetto di tornare quello di prima.

---

## 12. Milestone

Ognuno termina con un criterio di uscita verificabile. **Non si passa al
successivo senza aver soddisfatto il precedente.**

### M1 — Il motore (fondamenta)

`model/`, `engine/`, `export/folder.py`, `cli.py`. Nessuna UI.

> **Uscita:** `stemforge brano.mp3 --stems vocals,drums,bass,other` produce
> quattro WAV corretti; il test di ricostruzione (§11.2) passa; il tetto di
> 60 s (§6.1) è rispettato.

### M2 — App standalone

`worker/`, `ui/`, quattro schermate, packaging PyInstaller.

> **Uscita:** un `.app` che si apre con doppio click su un Mac pulito, senza
> Python installato, separa un brano e mostra i risultati. Annulla funziona
> entro 1 s.

### M3 — Consegna alla DAW

`export/ableton.py`, `reaper.py`, `aaf_export.py`, drag & drop.

> **Uscita — verifica manuale obbligatoria:** il `.als` generato si apre in
> Ableton Live, mostra una traccia per stem, colorata, al tempo corretto,
> con i sample risolti; premendo Play il risultato **suona identico al
> brano originale**. Questo è il momento in cui il progetto diventa
> davvero utile.

### M4 — Più strumenti

Backend RoFormer, cascata di 2° stadio, stem sperimentali attivati.

> **Uscita:** RoFormer batte `htdemucs_ft` in un test A/B in cieco su voce;
> l'invariante di ricostruzione regge anche a due stadi; ogni stem
> sperimentale è etichettato onestamente nell'UI.

### M5 — Rifinitura

Batch, preferenze, preview d'ascolto, notarizzazione.

> **Uscita:** 20 brani in coda senza perdite di memoria; app notarizzata
> che si apre su un Mac di terze parti senza avvisi di sicurezza.

---

## 13. Regole di scrittura del codice

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

## 14. Cose che questa spec non promette

Onestà preventiva. Ognuna di queste, scoperta a metà lavoro, costerebbe
molto più che saperla adesso.

**14.1 — Gli archi non verranno bene.** Non nella v1, forse mai come la
voce. È un limite dello stato dell'arte, non dell'implementazione. Per
questo esistono i badge "sperimentale" e la tabella di affidabilità: sono
parte del prodotto, non un disclaimer legale.

**14.2 — Il `.als` si romperà quando Ableton cambierà versione maggiore.**
Il template va rigenerato e il writer riverificato a ogni major di Live.
È il costo di un formato non documentato, ed è comunque molto inferiore al
costo di mantenere un plugin.

**14.3 — Il C++ non è in questa spec.** Il momento in cui avrà senso è
quando si vorrà eliminare torch dal bundle esportando i modelli in CoreML:
l'app scenderebbe da ~1 GB a ~200 MB e partirebbe in un secondo invece che
in cinque. È un lavoro autonomo, da fare **dopo** M5, non prima. Farlo
adesso rallenterebbe tutto senza migliorare nulla di percepibile.

**14.4 — Niente separazione in tempo reale.** Mai, con questa architettura.
Vedi §7.0.

**14.5 — Windows e Linux non sono target della v1.** Il codice resta
portabile (nessuna API macOS fuori da `ui/` e `packaging/`), ma packaging,
firma e test sono solo macOS. Aggiungere Windows dopo M5 è ragionevole;
farlo prima raddoppia il lavoro di packaging a metà progetto.
