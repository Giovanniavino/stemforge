# StemForge

Trascina un brano, spunta gli strumenti, premi **Separa**. Poi trascina
gli stem direttamente nel progetto Ableton (o qualunque DAW) già aperto.

Target: **macOS 10.15+ (Catalina) su Mac Intel, solo CPU** — va bene
anche un Mac mini del 2012. La qualità viene prima del tempo: il preset
di default è `Massima` e l'attesa — anche lunga — viene dichiarata
onestamente prima di partire, calibrata sulla velocità del tuo Mac.

Installazione: manda all'utente `dist/StemForge-Installer.zip`
(rigenerabile con `make installer`): doppio click su
"Installa StemForge.command" e fa tutto da solo.

## Uso (app)

1. Apri StemForge (al primo avvio scarica i modelli, ~1 GB, una volta sola).
2. Trascina un brano nella finestra.
3. Spunta gli strumenti. La stima del tempo si aggiorna a ogni spunta:
   chiedere meno costa meno.
4. Premi Separa. A fine corsa, seleziona gli stem e trascinali
   nell'arrangiamento: una traccia per file, allineati al campione.

Gli stem finiscono in `~/Music/StemForge/<nome brano>/` come WAV 24 bit
(o FLAC), con un `manifest.json` accanto. Nessun account, nessuna rete
dopo il primo avvio.

## Uso (CLI)

```
stemforge brano.mp3 --stems vocals,drums,bass,other
stemforge brano.mp3 --stems vocals --quality balanced   # ~1/4 del tempo
stemforge brano.mp3 --stems kick,snare --dry-run        # mostra il piano
```

Stem: `vocals drums bass guitar piano other instrumental` più i derivati
`kick snare toms hihat cymbals lead_vocals backing_vocals` (derivati e
de-riverbero arrivano con la milestone M6). Preset: `fast`, `balanced`,
`best` (default).

## Tempi misurati

| Macchina | Richiesta (`balanced`) | Tempo |
|---|---|---|
| dev-box x86 CPU (Windows) | 30 s di audio, solo `vocals` | 23 s |
| dev-box x86 CPU (Windows) | 30 s di audio, 4 stem | 130 s |
| **Mac Intel di riferimento** | *da misurare alla chiusura di M1 sul target* | — |

Il rapporto misurato fra "una traccia" e "tutto" è **0.18**: chiedere
poco costa poco (obiettivo O7). In `best` i tempi crescono di ~10x
rispetto a `balanced` con una sola traccia: è il prezzo dichiarato della
qualità massima, e la stima in app lo dice prima di partire.

## Sviluppo

```
make dev    # venv + dipendenze pinnate (hash verificati)
make test   # suite veloce (<10 s, senza modelli)
make test-slow  # con Demucs reale (scarica i pesi)
make build  # .app x86_64 via PyInstaller (solo su macOS)
```

Su Windows (dev-box): `py -3.12 -m venv .venv` e
`pip install -r requirements-dev-win.lock`.

La specifica completa, con ogni decisione e la sua ragione, è in
[BUILD_SPEC.md](BUILD_SPEC.md). Regole dure verificate dai test: nessun
file oltre 400 righe, dipendenze in una direzione sola, `model/` senza
I/O, UI senza engine.

## Idee

(qui finiscono le feature non in spec, §11 regola 10 — per ora niente)
