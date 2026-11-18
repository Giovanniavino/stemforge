# Problemi e domande

[← Indice della guida](README.md)

## Messaggi e cosa fare

Ogni messaggio di StemForge dice cosa fare. Qui sotto i casi più comuni,
con qualche dettaglio in più.

| Messaggio o sintomo | Cosa fare |
|---|---|
| "Memoria insufficiente" | Chiudi le altre app, oppure usa la qualità **Veloce**. Il lavoro si può rilanciare subito. |
| "Spazio su disco insufficiente" | StemForge controlla lo spazio **prima** di cominciare, in base a quello che hai chiesto: libera lo spazio indicato, o chiedi meno stem. |
| Il download dei modelli non riesce | Controlla la connessione. Un firewall o un proxy deve lasciar raggiungere `dl.fbaipublicfiles.com`. Poi riprova: un file rovinato da un download interrotto viene riconosciuto dal suo SHA-256 e riscaricato. |
| Un file viene rifiutato quando lo trascini | Il formato non è supportato, oppure non è audio. I file protetti da DRM (per esempio i vecchi acquisti `.m4p` di iTunes o i brani scaricati da Apple Music) non si possono leggere. |
| Avviso "quasi silenzioso" su uno stem | Quello strumento nel brano non c'è, o quasi. Il file viene scritto lo stesso. |
| In una coda di brani uno fallisce | Gli altri continuano; alla fine c'è un riepilogo con il nome del file e il motivo. |
| "Il file dura più di 30 minuti" | Taglialo prima nella DAW o in un editor audio: StemForge rifiuta i file oltre i 30 minuti. |
| Il file contiene valori non validi | Il file è danneggiato (contiene campioni che non sono numeri). Riesportalo dal programma da cui viene. |
| La stima era sbagliata | Migliora con ogni lavoro completato. Se è molto lontana dal vero, [esporta la diagnostica](#esportare-la-diagnostica) e apri una segnalazione. |
| La GPU del Mac Apple Silicon non viene usata | Al primo avvio la GPU ha dato un risultato diverso dalla CPU, quindi StemForge resta sulla CPU: è più lenta ma sempre esatta. La diagnostica contiene l'esito del controllo. |
| Trascinare nella DAW non fa niente | Trascina gli stem nell'area delle tracce o nell'arrangiamento, non sopra un plugin. Oppure usa **Mostra nel Finder / in Esplora file** e trascina da lì. |
| L'app non si apre la prima volta | È l'avviso del sistema per le app non firmate: vedi [Se l'app non si apre](installazione.md#se-lapp-non-si-apre). |

## Dove stanno i file

| | Modelli e calibrazione | Log |
|---|---|---|
| macOS | `~/Library/Application Support/StemForge/` | `~/Library/Logs/StemForge/` |
| Windows | `%LOCALAPPDATA%\StemForge\` | `%LOCALAPPDATA%\StemForge\logs\` |
| Linux | `~/.local/share/stemforge/` (o `$XDG_DATA_HOME/stemforge/`) | `~/.local/state/stemforge/` |

Gli stem separati stanno in `~/Music/StemForge/` (la cartella **Musica**),
una sottocartella per brano.

Su Windows i modelli stanno nella parte **locale** del profilo, mai in
quella Roaming: un GB di modelli e una calibrazione che descrive *questo*
computer non devono seguirti su altri PC.

Il log ruota da solo (tre file da 5 MB al massimo): non riempie il disco.

## Esportare la diagnostica

Se qualcosa non va, StemForge mette tutto quello che serve per capirlo in
un solo file. **Non viene mandato niente a nessuno**: il file lo salvi tu,
dove vuoi.

1. Nella schermata iniziale premi **Esporta diagnostica** (su Mac c'è anche
   la voce nel menu **Aiuto**).
2. Scegli dove salvare lo zip.
3. Se vuoi, aprilo e guarda cosa c'è dentro: il log, la versione di
   StemForge, il sistema, l'esito del collaudo interno (fatto senza rete)
   e l'esito del controllo della GPU. **Il log contiene i nomi dei brani
   che hai elaborato**: decidi tu se mandarlo e a chi.
4. Allegalo a una [segnalazione](#chiedere-aiuto).

Per chi è pratico del terminale, lo stesso collaudo si lancia così e scrive
l'esito in un file:

```bash
# macOS
/Applications/StemForge.app/Contents/MacOS/StemForge --selftest --offline --report ~/Desktop/selftest.txt
# Linux
./StemForge-<versione>-linux-x86_64.AppImage --selftest --offline --report ~/selftest.txt
```

Su Windows (Prompt dei comandi, dalla cartella di installazione — di solito
`%LOCALAPPDATA%\Programs\StemForge`):
`StemForge.exe --selftest --offline --report "%USERPROFILE%\Desktop\selftest.txt"`.
Senza `--offline` il collaudo prova anche la connessione HTTPS al server
dei modelli.

## Chiedere aiuto

- **Problemi e domande:** apri una segnalazione nella pagina
  [Issues](https://github.com/Giovanniavino/stemforge/issues/new/choose)
  del progetto (serve un account GitHub gratuito). Scegli "Bug report" e
  allega il file della diagnostica: senza, capire un problema è quasi
  impossibile. Puoi scrivere in italiano.
- **Richieste di funzioni:** prima leggi cosa StemForge **non** farà mai
  (sezione "Non-obiettivi" della [specifica](../../BUILD_SPEC.md#non-obiettivi--da-rifiutare-se-emergono-in-corso-dopera)):
  niente plugin, niente slicing o kit, niente effetti, niente cloud.

## Domande frequenti

**Manda la mia musica da qualche parte?** No. La separazione avviene tutta
sul tuo computer. L'unica connessione che StemForge fa è il download dei
modelli al primo avvio. Niente account, niente telemetria, niente
aggiornamenti automatici. Vedi [PRIVACY.md](../../PRIVACY.md).

**Con quali DAW funziona?** Con qualunque DAW che accetti file trascinati
dal desktop: StemForge usa il drag & drop del sistema operativo, senza
codice specifico per una DAW. Gli obiettivi sono Ableton Live, Logic Pro,
FL Studio, Reaper, Cubase, Studio One e Bitwig. Il drag & drop non si può
collaudare in automatico: ogni DAW si prova a mano con una lista di
controllo, e le note di ogni versione dicono quali combinazioni sono state
provate.

**Perché non è un plugin VST/AU?** Un plugin gira nel thread audio della
DAW, con pochi millisecondi per buffer e il divieto di allocare memoria.
La separazione con le reti neurali richiede minuti e gigabyte di RAM: le
due cose sono incompatibili. Anche i prodotti che offrono la separazione
"dentro un plugin" in realtà elaborano fuori tempo reale e restituiscono
dei file, esattamente come StemForge.

**Usa la mia scheda video NVIDIA / AMD / Intel su Windows o Linux?** Non in
questa versione. Un PyTorch per GPU pesa circa 2,5 GB, più del limite di
2 GB per file delle release di GitHub, e sarebbe un download enorme per chi
quella GPU non ce l'ha. L'accelerazione AMD/Intel su Windows (DirectML) non
sa eseguire l'operazione centrale dei modelli. Si usa solo la GPU dei Mac
Apple Silicon, e solo dopo che ha dimostrato di dare lo stesso risultato
della CPU.

**Perché è così lento sul mio Mac vecchio?** Perché la qualità viene
prima: la qualità predefinita dà gli stem migliori che i modelli sanno
produrre. Quando hai fretta usa **Bilanciata** o **Solo voce**: la stima ti
fa vedere subito quanto risparmi.

**Posso usare il computer mentre separa?** Sì. StemForge lavora in un
processo separato e l'interfaccia resta reattiva; il lavoro sarà solo un
po' più lento.

**Che fine fanno i file quando li trascino nella DAW?** Restano nella
cartella di StemForge: trascinare non li sposta. Se la DAW li copia nella
cartella del progetto o li usa da dove sono dipende dalle sue impostazioni.

**Può fare kit di batteria, slice, loop, o togliere il riverbero da un
mix?** No: StemForge separa e consegna gli stem, nient'altro. Slicing,
kit, effetti ed editing sono lavoro della DAW o del campionatore. (L'unica
eccezione è l'opzione **Togli il riverbero** sulla *voce già separata*,
quando il suo modello sarà disponibile: e anche allora StemForge scrive
anche la versione originale, `vocals_wet`.)

**È gratis?** Sì, ed è software libero con licenza MIT. Se ti è utile, vedi
[Sostenere il progetto](#sostenere-il-progetto).

## Sostenere il progetto

StemForge è gratuito e lo resterà. I link per le donazioni non sono ancora
attivi: quando ci saranno, compariranno qui, nel README e come pulsante
**Sponsor** della pagina GitHub del progetto.
