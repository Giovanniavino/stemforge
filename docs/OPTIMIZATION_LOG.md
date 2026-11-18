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
| — | nessun tentativo registrato finora | | | | | |
