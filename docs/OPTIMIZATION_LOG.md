# Registro delle ottimizzazioni

BUILD_SPEC §11 regola 12 e §6: si ottimizza solo misurando. Ogni
tentativo, **accettato o scartato**, ha una riga qui.

Regole per accettare un tentativo:

- profilo prima di cambiare il codice: si ottimizza ciò che il profilo
  indica, non ciò che sembra lento;
- guadagno ≥ 5% sulla **mediana di 5 ripetizioni** con `device=cpu`
  (mai numeri misurati su CUDA: BUILD_SPEC D6);
- risultato identico: bit per bit fuori dall'inferenza, scarto
  < −90 dBFS dentro l'inferenza.

| Data | Cosa | Profilo / macchina (`device=cpu`) | Mediana prima → dopo | Risultato identico? | Esito | Commit |
|---|---|---|---|---|---|---|
| 2026-11-27 | O1.1 — la voce del 1° stadio torna al sample rate originale una volta sola | dev-box Ryzen 5 5625U, Windows 11; pipeline con backend finto, 180 s a 48 kHz, 4 stem, WAV | CPU 9,81 → 9,09 s (−7,3%); picco RAM oltre gli import 1115 → 1014 MB | sì, SHA-256 degli stem uguale | accettato | 6aeb012 |
| 2026-11-27 | O1.2 — l'assemblaggio libera gli stem intermedi man mano | come O1.1, A = O1.1 | picco RAM oltre gli import 1014 → 752 MB (−25,9%) | sì, SHA-256 degli stem uguale | accettato | a9cfdee |
| 2026-11-27 | O2.1 — in RAM solo i sotto-modelli del bag che la passata usa, gli altri liberati prima di caricare i mancanti | dev-box; `run_job` reale, 30 s di audio, picco del working set, A/B alternati | solo voce (`balanced`): MODERNO 1894,8 → 1359,6 MB (−28,2%), LEGACY 1612,8 → 1189,3 MB (−26,3%); 4 stem `best`: invariato (servono tutti e 4) | sì, SHA-256 uguale (voce; `best` con seme fisso) | accettato | 6a37914 |
| 2026-11-27 | O3.1 — `engine.calibrate` (e numpy) fuori dall'avvio della finestra | dev-box; finestra offscreen, tempo CPU del processo | MODERNO 0,938 → 0,688 s (−27%); LEGACY 1,031 → 0,984 s (−5%, nel rumore: shiboken 6.4 importa numpy da sé) | sì, nessun calcolo cambiato | accettato | d6a8c62 |
| 2026-11-27 | O4.1 — scansione delle cartelle trascinate dai `DirEntry` | dev-box; `_collect_audio_files`, 100/1000/5000 voci | 5000 voci: MODERNO 1556 → 343 ms, LEGACY 2521 → 310 ms (78–88%) | sì, stessi file, stesso ordine | accettato | e355c39 |
| 2026-11-27 | O4.2 — durata del brano letta in un thread dopo il drop | dev-box; drop di un m4a di 30 s, thread principale fermo | MODERNO 168,5 → 2,6 ms; LEGACY 140,4 → 0,7 ms (~98%) | sì, stessa durata al picker | accettato | 4e6ad61 |
| 2026-11-27 | O5 — ruff e mypy strict concordati, `make lint`, duplicati e funzioni vicine al tetto (interventi 1–3, 5–8) | test esistenti non toccati, entrambi i venv | comportamento invariato (piani identici byte per byte su 98 298 casi, PNG dell'icona identico) | sì | accettato | 1c4e24c, 2cae11a |
| 2026-11-27 | O5 — codice morto (`FOLDERID_MUSIC`), classe base per i backend di 2° stadio, mixin `changeEvent`, regole ruff UP, spezzare `Demucs4Backend.separate` (interventi 4, 9–12) | — | — | — | scartati: falsi positivi, astrazioni che la spec non chiede, stile senza effetto, rischio numerico nell'inferenza | — |

I dettagli (comandi, singole misure, profili di partenza) stanno nei
registri per area: [O1](optimization/O1.md), [O2](optimization/O2.md),
[O3](optimization/O3.md), [O4](optimization/O4.md), [O5](optimization/O5.md).

## Decisioni per il committente

Nessun agente ha proposto di rimettere in discussione la lista
"Cosa NON fare" (§6.2): niente `torch.compile`, `segment` più grande,
brani in parallelo, fp16 su CPU o tagli a `shifts`/`overlap` in `best`.

Punti aperti, misurati ma non tentati:

- O1: la scrittura degli stem (`folder.write_stem`, conversione
  float→PCM_24 e `rms_dbfs` in float64) pesa ~3,3 s su 5,6 s fuori dal
  modello.
- O2: in `best` il picco scende solo caricando i sotto-modelli uno alla
  volta durante la passata; non tentato (§6.1 punto 2, vedi O2.md).
- O3: avvio e dimensione del pacchetto congelato win-x64 non misurati.
- O4: il primo "Ascolta" ferma l'UI 412–1254 ms (creazione di
  QMediaPlayer + QAudioOutput).
- O5: le eccezioni ruff nei test (F811, I001, F401, B007, B023, B905,
  SIM102) restano finché un giro può toccare `tests/`.
- Misure sul Mac mini 2012 del profilo legacy-intel: non eseguite, serve
  l'hardware.
