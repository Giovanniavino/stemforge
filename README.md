<h1 align="center">StemForge</h1>

<p align="center">
  <em>Separa un brano nelle sue tracce. Trascinale nel tuo progetto. Fine.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-in%20sviluppo-orange" alt="status">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Apple%20Silicon-black" alt="platform">
  <img src="https://img.shields.io/badge/python-3.12-blue" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

---

Un'app desktop che prende una canzone, la separa negli strumenti che scegli,
e te li fa trascinare direttamente nel progetto Ableton che hai già aperto.

Niente plugin da installare, niente progetto nuovo da aprire, niente import.
Trascini e continui a lavorare.

## Come funziona

```
  brano.mp3  ─→  scegli gli strumenti  ─→  ⌘ drag  ─→  il tuo progetto
```

1. Trascini un brano dentro l'app
2. Spunti cosa ti serve — solo la voce, o tutto
3. Trascini gli stem nell'arrangiamento

## Il tempo scala con quello che chiedi

Questa è la scelta di design che guida il progetto: chiedere una traccia
sola deve costare una frazione di chiederle tutte, non lo stesso tempo con
meno file in uscita.

| Richiesta | Tempo su M1 |
|---|---|
| solo voce | **~18 s** |
| voce + batteria | ~32 s |
| voce · batteria · basso · altro | ~60 s |
| tutto, batteria scomposta inclusa | ~85 s |

## Tracce

**Base** — voce, batteria, basso, chitarra, piano, altro, strumentale

**Dettaglio** *(opzionale, costa una passata in più)*
- batteria → kick, snare, toms, hi-hat, cymbals
- voce → lead, cori, rimozione riverbero

## Stato

In sviluppo. La specifica di costruzione completa è in
**[BUILD_SPEC.md](BUILD_SPEC.md)**: architettura, motore, interfaccia,
packaging e milestone con criteri di uscita verificabili.

| Milestone | |
|---|---|
| M1 · motore e CLI | 🔨 |
| M2 · app standalone | ⬜ |
| M3 · drag & drop | ⬜ |
| M4 · qualità (RoFormer) | ⬜ |
| M5 · rifinitura | ⬜ |
| M6 · tracce di dettaglio | ⬜ |

## Perché non è un plugin VST

Un plugin gira nel thread audio della DAW, con pochi millisecondi per
buffer e il divieto di allocare memoria. La separazione neurale richiede
decine di secondi e gigabyte di RAM. Non è un limite dell'implementazione:
è incompatibilità di natura.

Ogni prodotto che offre separazione "dentro un plugin" fa esattamente
quello che fa StemForge — elabora offline e consegna file.

## Costruito su

[Demucs](https://github.com/adefossez/demucs) di Alexandre Défossez e
Meta AI Research, [PyTorch](https://pytorch.org), [Qt](https://www.qt.io).

## Licenza

MIT — vedi [LICENSE](LICENSE).
