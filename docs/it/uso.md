# Uso

[← Indice della guida](README.md)

StemForge ha quattro schermate e nient'altro: niente menu di preferenze
annidati. Tutto si fa anche da tastiera.

## 1. Scegli il brano

Trascina un brano nella zona grande al centro, oppure fai click per
sceglierlo (scorciatoia: **Cmd+O** su Mac, **Ctrl+O** su Windows e Linux).

- Formati accettati: `wav`, `mp3`, `flac`, `ogg`, `m4a`, `aiff`, `aif`.
- Puoi trascinare **più file** o **intere cartelle**: verranno separati in
  fila, uno dopo l'altro. Se uno fallisce, gli altri continuano e alla
  fine hai un riepilogo.
- Un file che non è audio viene rifiutato subito, con un messaggio nella
  finestra.
- Su Mac puoi anche usare **Apri con → StemForge** dal Finder; su Windows
  la stessa voce c'è in Esplora file.

## 2. Scegli gli strumenti

È la schermata in cui decidi quanto tempo vuoi spendere.

- In alto due scorciatoie: **Tutto** (la resa completa) e **Solo voce** (il
  lavoro veloce: imposta anche il preset **Bilanciata**).
- Sotto, le card degli strumenti: **voce, batteria, basso, chitarra,
  piano, altro, strumentale**. Voce, batteria, basso e altro sono già
  spuntati.
- **Strumentale** è tutto tranne la voce, in un file solo: la base per il
  karaoke o per un remix.
- I dettagli della batteria (cassa, rullante, tom, hi-hat, piatti) e della
  voce (voce principale, cori, togliere il riverbero) compaiono solo quando
  i loro modelli superano la prova d'ascolto: un'opzione che non suona bene
  non viene mostrata.

In fondo ci sono due soli controlli:

- **Qualità**:
  - **Massima** *(predefinita)*: usa sempre l'insieme completo dei
    modelli, senza scorciatoie. È la scelta per il lavoro finito.
  - **Bilanciata**: più veloce, perché fa girare solo le parti del modello
    che servono a ciò che hai spuntato.
  - **Veloce**: per un'anteprima o per provare tanti brani.
- **Formato**: WAV o FLAC, sempre a 24 bit.

### La stima del tempo

In basso, sempre visibile, c'è la stima: per esempio *"~14 min · 4
passate"*. Si aggiorna a ogni spunta e **scende quando togli qualcosa**:
chiedere meno costa meno.

La stima viene dalla calibrazione fatta al primo avvio sul **tuo**
computer, non da numeri misurati su un'altra macchina, e migliora con ogni
brano che separi. È volutamente pessimista del 15%: finire prima del
previsto è un piacere, dopo è un difetto. Con la qualità Massima su un Mac
vecchio la stima può dire "più di un'ora": è la verità, e la Bilanciata è
a un click.

Premi **Separa** (o **Invio**).

## 3. Avanzamento

- La barra mostra la fase in parole: *"Separazione — passata 2 di 3"*,
  *"Scrittura stem"*.
- Il tempo rimanente si aggiorna ogni pochi secondi; sulle attese lunghe
  vedi anche l'orario previsto di fine (*"~35 min — pronto verso le
  15:40"*).
- **Annulla** (o **Esc**) è sempre attivo: il lavoro si ferma entro un
  secondo, i file a metà vengono cancellati e torni alla scelta degli
  strumenti con le tue spunte intatte.

Puoi usare il computer per altro mentre StemForge lavora; sarà solo un po'
più lento.

## 4. Risultato: trascina nella DAW

Questa è la schermata da cui si trascina.

- Vedi l'elenco degli stem con durata e picco in dBFS.
- **Anteprima**: play/stop, uno stem alla volta, per sentire cosa stai per
  trascinare.
- **Seleziona uno o più stem e trascinali** nell'arrangiamento della tua
  DAW: in un solo gesto ottieni una traccia per file, già allineata al
  campione con il brano originale. Il drag funziona anche se in primo piano
  c'è la DAW: non serve cliccare prima su StemForge.
- Il trascinamento **copia**: i file restano anche nella cartella di
  StemForge.
- **Mostra nel Finder** (Mac), **Mostra in Esplora file** (Windows),
  **Mostra nella cartella** (Linux) apre la cartella con lo stem già
  evidenziato, per chi preferisce trascinare da lì o copiare i file
  altrove.

StemForge è pensato per Ableton Live, Logic Pro, FL Studio, Reaper,
Cubase, Studio One e Bitwig, e funziona con qualunque programma che accetti
file trascinati dal desktop.

## Dove finiscono i file

```
Musica/StemForge/Nome del brano/
  vocals.wav
  drums.wav
  bass.wav
  other.wav
  manifest.json
```

- La cartella si chiama come il brano; se esiste già, StemForge aggiunge
  ` (2)` invece di sovrascrivere.
- I nomi dei file sono quelli degli stem in inglese, minuscoli e senza
  spazi (`vocals`, `drums`, `bass`, `guitar`, `piano`, `other`,
  `instrumental`): la DAW li usa come nomi delle tracce.
- Gli stem hanno **lo stesso sample rate e la stessa lunghezza in campioni**
  dell'originale. Niente normalizzazione, niente limiter, niente
  dissolvenze: sommati, ricostruiscono il mix. Il mix si fa nella DAW.
- `manifest.json` serve a StemForge per riaprire il risultato senza
  ricalcolare niente.

## Quanto ci vuole

Non esiste un numero valido per tutti: la separazione gira sulla CPU (o,
sui Mac Apple Silicon, sulla GPU verificata) e i computer sono molto
diversi fra loro. Per questo StemForge ti dà la stima calibrata sul tuo.
Le proporzioni invece valgono ovunque:

- in **Bilanciata**, la sola voce costa circa **un quarto** dei quattro
  stem base; voce e batteria circa **la metà**;
- i dettagli di batteria e voce aggiungono passate corte;
- la **Massima** costa circa **tre volte** la separazione completa in
  Bilanciata. Su un Mac Intel di qualche anno fa può voler dire più di
  un'ora per un brano: è il prezzo dichiarato della qualità massima.

## Casi particolari

- **Brani mono** restano mono.
- **File 5.1 / 7.1**: vengono ridotti a stereo (te lo dice) e gli stem sono
  stereo.
- **Brani oltre i 15 minuti** si elaborano a blocchi che si raccordano
  senza giunzioni; **oltre i 30 minuti** vengono rifiutati, con il motivo.
- **Tracce quasi silenziose**: se uno strumento nel brano non c'è, lo stem
  viene scritto lo stesso e l'app ti avvisa che è quasi muto.

## Lingua e accessibilità

- L'interfaccia è in italiano e in inglese e segue la lingua del sistema.
- Si usa tutta da tastiera: **Tab** per spostarsi, **Invio** = Separa,
  **Esc** = Annulla/Indietro, **Cmd/Ctrl+O** = scegli file.
- Funziona con VoiceOver (Mac) e NVDA (Windows); segue il tema chiaro o
  scuro del sistema.

Qualcosa non va? Vedi [Problemi e domande](problemi.md).
