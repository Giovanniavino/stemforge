# Privacy

*[Versione italiana più sotto](#privacy-in-italiano).*

**StemForge collects nothing.** It has no account, no telemetry, no
analytics, no crash reporter and no auto-update. Your music never leaves
your computer: separation runs entirely on your own CPU (or, on Apple
Silicon, your own GPU).

## The only network connections

| When | To | What is sent | What is received |
|---|---|---|---|
| First launch (and again only if a model file is missing or damaged) | `dl.fbaipublicfiles.com`, the official server of the Demucs models, run by Meta | an ordinary HTTPS download request for the model files: your IP address and a standard request header reach that server, as with any download | the model files (about 1 GB), each checked against a SHA-256 fixed in the code |
| Only if you run `StemForge --selftest` **without** `--offline` (the diagnostics export always uses `--offline`) | the same server | one HTTPS `HEAD` request, to check that the connection works; then, if the models are not downloaded yet, the same model download as above, for a short test separation | the model files, if they were missing |

Nothing about you, your computer or your songs is sent in either case.
StemForge does not set cookies and has no identifier of any kind. The
model server is operated by Meta, not by StemForge: its own logs, if any,
are governed by Meta's policies.

Once the models are downloaded, StemForge works offline forever. You can
block it in your firewall after the first launch and nothing changes.

If future versions adopt more models (BUILD_SPEC §5.8), each one will be
downloaded the same way, from a fixed address at an immutable revision,
and listed in this file before release.

## What stays on your computer

| What | Where (macOS · Windows · Linux) |
|---|---|
| Your stems and their `manifest.json` | `~/Music/StemForge/` |
| Models and the speed calibration of this computer | `~/Library/Application Support/StemForge/` · `%LOCALAPPDATA%\StemForge\` · `~/.local/share/stemforge/` |
| Log (rotated: at most 3 files of 5 MB) | `~/Library/Logs/StemForge/` · `%LOCALAPPDATA%\StemForge\logs\` · `~/.local/state/stemforge/` |

The log contains the **names of the songs you processed**, the steps of
each job and any errors. It is never sent anywhere.

## Diagnostics

**Export diagnostics** creates a zip with the log, the StemForge version,
your operating system, the result of the offline self-test and the result
of the GPU check. It is saved **where you choose**, and nothing is
uploaded: you can open it, read it, and decide whether to send it and to
whom (for example by attaching it to a GitHub issue). Remember that it
contains the names of your songs; rename or remove them from the log
first if you prefer.

## GitHub

Downloading StemForge from GitHub or opening an issue there is subject to
[GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement),
not to StemForge's. Anything you write or attach in an issue is public.

---

## Privacy in italiano

**StemForge non raccoglie niente.** Niente account, telemetria, statistiche
d'uso, invio automatico dei crash o aggiornamenti automatici. La tua
musica non esce mai dal tuo computer: la separazione gira tutta sulla tua
CPU (o, sui Mac Apple Silicon, sulla tua GPU).

**Le uniche connessioni:**

- **al primo avvio** (e di nuovo solo se un file dei modelli manca o è
  rovinato) StemForge scarica i modelli, circa 1 GB, da
  `dl.fbaipublicfiles.com`, il server ufficiale dei modelli Demucs gestito
  da Meta. È un normale download HTTPS: a quel server arrivano il tuo
  indirizzo IP e un'intestazione di richiesta standard, come per qualsiasi
  download. Ogni file è controllato con uno SHA-256 fissato nel codice;
- **solo se lanci** `StemForge --selftest` **senza** `--offline`: una
  richiesta HTTPS `HEAD` allo stesso server, per provare che la connessione
  funziona, e, se i modelli non sono ancora stati scaricati, lo stesso
  download dei modelli, per una breve separazione di prova. L'esportazione
  della diagnostica usa sempre `--offline`.

In nessuno dei due casi viene mandato qualcosa su di te, sul tuo computer o
sui tuoi brani. Dopo il download StemForge funziona offline per sempre:
puoi anche bloccarlo nel firewall.

**Cosa resta sul tuo computer:** gli stem (`~/Music/StemForge/`), i modelli
e la calibrazione, e il log, nelle cartelle della tabella qui sopra. Il log
contiene **i nomi dei brani elaborati** e non viene mai mandato da nessuna
parte.

**Diagnostica:** "Esporta diagnostica" crea uno zip con log, versione,
sistema, esito del collaudo senza rete e del controllo della GPU, e lo
salva **dove scegli tu**. Non viene caricato niente: lo apri, lo leggi e
decidi tu se mandarlo e a chi. Contiene i nomi dei tuoi brani.

**GitHub:** scaricare StemForge da GitHub o aprire una segnalazione lì è
regolato dall'informativa di GitHub, non da questa. Ciò che scrivi o
alleghi in una segnalazione è pubblico.
