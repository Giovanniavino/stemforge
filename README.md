<h1 align="center">StemForge</h1>

<p align="center">
  <em>Separa un brano nelle sue tracce. Trascinale nel progetto che hai già aperto. Fine.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS%2010.15%2B%20Intel-black" alt="platform">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="python">
  <img src="https://img.shields.io/badge/milestone-M1--M3%20completate-brightgreen" alt="milestone">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

---

Trascina un brano, spunta gli strumenti, premi **Separa**. Poi trascina gli
stem direttamente nel progetto Ableton — o qualunque DAW — già aperto.

Niente plugin da installare, niente progetto nuovo da aprire, niente import.

```
  brano.mp3  ─→  scegli gli strumenti  ─→  drag  ─→  il tuo progetto
```

## Su che macchine gira

Target: **macOS 10.15+ (Catalina), Mac Intel, solo CPU** — va bene anche un
Mac mini del 2012.

La qualità viene prima del tempo: il preset di default è `Massima`, e
l'attesa — anche lunga — viene dichiarata onestamente prima di partire,
calibrata sulla velocità del tuo Mac.

## Installazione

Manda all'utente `dist/StemForge-Installer.zip`, rigenerabile con
`make installer`. Doppio click su **"Installa StemForge.command"** e fa
tutto da solo.

Al primo avvio l'app scarica i modelli (~1 GB, una volta sola). Dopo di
quello non tocca più la rete: nessun account, nessuna telemetria.

## Uso

1. Trascina un brano nella finestra.
2. Spunta gli strumenti. **La stima del tempo si aggiorna a ogni spunta:
   chiedere meno costa meno.**
3. Premi Separa.
4. A fine corsa seleziona gli stem e trascinali nell'arrangiamento: una
   traccia per file, allineati al campione.

Gli stem finiscono in `~/Music/StemForge/<nome brano>/` come WAV 24 bit o
FLAC, con un `manifest.json` accanto.

### Da riga di comando

```bash
stemforge brano.mp3 --stems vocals,drums,bass,other
stemforge brano.mp3 --stems vocals --quality balanced   # ~1/4 del tempo
stemforge brano.mp3 --stems kick,snare --dry-run        # mostra il piano
```

## Tracce

**Base** — `vocals` `drums` `bass` `guitar` `piano` `other` `instrumental`

**Derivate** — `kick` `snare` `toms` `hihat` `cymbals` `lead_vocals`
`backing_vocals`, più il de-riverbero della voce *(in arrivo con M6)*

Preset: `fast`, `balanced`, `best` *(default)*.

## Il tempo scala con quello che chiedi

È la scelta di design che guida il progetto: chiedere una traccia sola deve
costare una frazione di chiederle tutte, non lo stesso tempo con meno file
in uscita.

| Macchina | Richiesta (`balanced`) | Tempo |
|---|---|---|
| dev-box x86 CPU (Windows) | 30 s di audio, solo `vocals` | 23 s |
| dev-box x86 CPU (Windows) | 30 s di audio, 4 stem | 130 s |
| Mac Intel di riferimento | *da misurare sul target* | — |

Il rapporto misurato fra "una traccia" e "tutto" è **0.18**. In `best` i
tempi crescono di circa 10x rispetto a `balanced`: è il prezzo dichiarato
della qualità massima, e la stima in app lo dice prima di partire.

## Stato

| Milestone | |
|---|---|
| M1 · motore, pianificatore, CLI | ✅ |
| M2 · app standalone | ✅ |
| M3 · drag & drop | ✅ |
| M4 · qualità (RoFormer) | ⬜ |
| M5 · rifinitura e notarizzazione | ⬜ |
| M6 · tracce derivate | ⬜ |

## Sviluppo

```bash
make dev        # venv + dipendenze pinnate (hash verificati)
make test       # suite veloce (<10 s, senza modelli)
make test-slow  # con Demucs reale (scarica i pesi)
make build      # .app x86_64 via PyInstaller (solo su macOS)
```

Su Windows (dev-box): `py -3.12 -m venv .venv` e
`pip install -r requirements-dev-win.lock`.

La specifica completa, con ogni decisione e la sua ragione, è in
**[BUILD_SPEC.md](BUILD_SPEC.md)**.

Regole dure verificate dai test: nessun file oltre 400 righe, dipendenze in
una direzione sola, `model/` senza I/O, UI senza engine.

## Perché non è un plugin VST

Un plugin gira nel thread audio della DAW, con pochi millisecondi per buffer
e il divieto di allocare memoria. La separazione neurale richiede decine di
secondi e gigabyte di RAM. Non è un limite dell'implementazione: è
incompatibilità di natura.

Ogni prodotto che offre separazione "dentro un plugin" fa esattamente quello
che fa StemForge — elabora offline e consegna file.

## Costruito su

[Demucs](https://github.com/adefossez/demucs) di Alexandre Défossez e Meta
AI Research · [PyTorch](https://pytorch.org) · [Qt](https://www.qt.io)

## Licenza

MIT — vedi [LICENSE](LICENSE).
