"""Il catalogo dei testi del worker: italiano e inglese (BUILD_SPEC §8.6).

Solo dati: la logica (lingua corrente, riserva, formattazione) sta in
i18n.py. Le due tabelle hanno le STESSE chiavi con gli STESSI segnaposto:
lo verifica tests/unit/test_engine_i18n.py, così nessun testo resta a
metà fra due lingue.
"""

from __future__ import annotations

IT: dict[str, str] = {
    # -- errori (§10.1): ognuno dice cosa fare ------------------------------
    "err.corrupt": (
        "{name}: il file è danneggiato o non contiene audio. Prova ad aprirlo "
        "in un lettore; se non suona, riesportalo o convertilo in WAV."
    ),
    "err.drm": (
        "{name} è protetto da DRM e non si può separare. Usa una copia "
        "senza protezione (per esempio esportata dalla tua DAW)."
    ),
    "err.unsupported": (
        "{name}: formato non supportato. Convertilo in WAV, FLAC o MP3 e riprova."
    ),
    "err.ffmpeg_missing": (
        "{name}: per questo formato serve il decoder dell'app, che non è "
        "disponibile. Converti il file in WAV, FLAC o MP3, oppure reinstalla StemForge."
    ),
    "err.empty": "{name} non contiene audio: scegli un altro file.",
    "err.channels": (
        "{name} ha {channels} canali: StemForge ne gestisce fino a 8. "
        "Esportalo in stereo o in 5.1 e riprova."
    ),
    "err.too_long": (
        "{name} dura {minutes} minuti: StemForge separa brani fino a 30 minuti. "
        "Taglialo nella DAW e riprova."
    ),
    "err.non_finite": (
        "{name} contiene campioni non validi (NaN o infinito) e non si può "
        "separare. Riesportalo dalla DAW o dal programma che l'ha creato."
    ),
    "err.disk_precheck": (
        "Spazio su disco insufficiente in {folder}: servono circa {needed} MB "
        "e ce ne sono {free} MB. Libera spazio o scegli un'altra cartella."
    ),
    "err.disk_full": (
        "Il disco si è riempito durante la scrittura degli stem. Libera spazio "
        "e rilancia la separazione."
    ),
    "err.memory": (
        "Memoria insufficiente: chiudi altre applicazioni o riprova con il "
        "preset Veloce."
    ),
    "err.model_unavailable": (
        "Non riesco a caricare il modello di separazione. Serve la connessione "
        "a internet una sola volta per scaricarlo: collegati e riprova."
    ),
    "err.device_unavailable": (
        "Il dispositivo di calcolo {device} non è disponibile su questo "
        "computer: scegli Automatico o CPU."
    ),
    "err.invalid_request": "Richiesta non valida: riavvia StemForge e riprova.",
    "err.generic": (
        "Elaborazione non riuscita. Riprova; se succede ancora, esporta la "
        "diagnostica e allegala alla segnalazione."
    ),
    "err.not_found": "{name}: file non trovato. Controlla il percorso.",
    # -- primo avvio (§9.4) --------------------------------------------------
    "prepare.offline": (
        "Per il primo avvio serve la connessione a internet (una sola volta, "
        "per scaricare i modelli). Collegati e riapri StemForge."
    ),
    "prepare.disk": "Spazio su disco insufficiente per i modelli (~1 GB): libera spazio e riapri.",
    "prepare.generic": (
        "Preparazione non riuscita: puoi comunque usare l'app, i modelli "
        "verranno riscaricati al prossimo avvio. Dettagli nel log."
    ),
    # -- avvisi non bloccanti -------------------------------------------------
    "warn.downmix": (
        "{name} ha {channels} canali: l'ho ridotto a stereo (downmix ITU-R "
        "BS.775, LFE escluso). Gli stem sono stereo."
    ),
    "warn.accel_fallback": (
        "L'accelerazione {device} non ha funzionato su questo brano: ho "
        "continuato sulla CPU (più lento, stesso risultato)."
    ),
    "warn.nearly_silent": "{file} è quasi silenzioso (picco {peak} dBFS).",
    "warn.missing_input": "{label}: manca lo stem di partenza, passata saltata.",
    "warn.unavailable.drumsplit": (
        "Il dettaglio batteria non è ancora disponibile in questa versione: "
        "ottieni comunque lo stem batteria completo."
    ),
    "warn.unavailable.vocalsplit": (
        "La separazione voce principale/cori non è ancora disponibile in "
        "questa versione: ottieni comunque lo stem voce completo."
    ),
    "warn.unavailable.dereverb": (
        "Il de-riverbero non è ancora disponibile in questa versione: la "
        "voce resta com'è."
    ),
    # -- fasi (§8.3) ----------------------------------------------------------
    "phase.demucs4": "Separazione",
    "phase.drumsplit": "Dettaglio batteria",
    "phase.dereverb": "De-riverbero voce",
    "phase.vocalsplit": "Dettaglio voce",
    "phase.pass": "{label} — passata {index} di {count}",
    "phase.writing": "Scrittura stem",
    "phase.download": "Scarico il modello {name}",
    "phase.calibrate": "Misuro la velocità di questo computer per darti stime oneste",
    # -- CLI -------------------------------------------------------------------
    "cli.done": "fatto: {path}",
    "cli.warning": "avviso: {message}",
    "cli.error": "errore su {name}: {message}",
    "cli.summary": "riepilogo errori:",
    "cli.cancelled": "annullato",
}

EN: dict[str, str] = {
    "err.corrupt": (
        "{name}: the file is damaged or contains no audio. Try opening it in "
        "a player; if it does not play, export it again or convert it to WAV."
    ),
    "err.drm": (
        "{name} is DRM-protected and cannot be separated. Use an unprotected "
        "copy (for example one exported from your DAW)."
    ),
    "err.unsupported": "{name}: unsupported format. Convert it to WAV, FLAC or MP3 and try again.",
    "err.ffmpeg_missing": (
        "{name}: this format needs the app's decoder, which is not available. "
        "Convert the file to WAV, FLAC or MP3, or reinstall StemForge."
    ),
    "err.empty": "{name} contains no audio: choose another file.",
    "err.channels": (
        "{name} has {channels} channels: StemForge handles up to 8. "
        "Export it as stereo or 5.1 and try again."
    ),
    "err.too_long": (
        "{name} is {minutes} minutes long: StemForge separates songs up to 30 "
        "minutes. Trim it in your DAW and try again."
    ),
    "err.non_finite": (
        "{name} contains invalid samples (NaN or infinity) and cannot be "
        "separated. Export it again from your DAW or from the program that made it."
    ),
    "err.disk_precheck": (
        "Not enough disk space in {folder}: about {needed} MB are needed and "
        "{free} MB are free. Free up space or choose another folder."
    ),
    "err.disk_full": (
        "The disk filled up while writing the stems. Free up space and run "
        "the separation again."
    ),
    "err.memory": "Not enough memory: close other applications or try again with the Fast preset.",
    "err.model_unavailable": (
        "The separation model cannot be loaded. An internet connection is "
        "needed once to download it: connect and try again."
    ),
    "err.device_unavailable": (
        "The compute device {device} is not available on this computer: "
        "choose Automatic or CPU."
    ),
    "err.invalid_request": "Invalid request: restart StemForge and try again.",
    "err.generic": (
        "Processing failed. Try again; if it happens again, export the "
        "diagnostics and attach them to your report."
    ),
    "err.not_found": "{name}: file not found. Check the path.",
    "prepare.offline": (
        "The first start needs an internet connection (only once, to download "
        "the models). Connect and reopen StemForge."
    ),
    "prepare.disk": "Not enough disk space for the models (~1 GB): free up space and reopen.",
    "prepare.generic": (
        "Preparation failed: you can still use the app, the models will be "
        "downloaded again at the next start. Details in the log."
    ),
    "warn.downmix": (
        "{name} has {channels} channels: I mixed it down to stereo (ITU-R "
        "BS.775 downmix, LFE excluded). The stems are stereo."
    ),
    "warn.accel_fallback": (
        "{device} acceleration failed on this song: I continued on the CPU "
        "(slower, same result)."
    ),
    "warn.nearly_silent": "{file} is nearly silent (peak {peak} dBFS).",
    "warn.missing_input": "{label}: the source stem is missing, pass skipped.",
    "warn.unavailable.drumsplit": (
        "Drum detail is not available in this version yet: you still get "
        "the full drums stem."
    ),
    "warn.unavailable.vocalsplit": (
        "Lead/backing vocal separation is not available in this version yet: "
        "you still get the full vocals stem."
    ),
    "warn.unavailable.dereverb": (
        "De-reverb is not available in this version yet: the vocals stay as they are."
    ),
    "phase.demucs4": "Separation",
    "phase.drumsplit": "Drum detail",
    "phase.dereverb": "Vocal de-reverb",
    "phase.vocalsplit": "Vocal detail",
    "phase.pass": "{label} — pass {index} of {count}",
    "phase.writing": "Writing stems",
    "phase.download": "Downloading the {name} model",
    "phase.calibrate": "Measuring this computer's speed to give you honest estimates",
    "cli.done": "done: {path}",
    "cli.warning": "warning: {message}",
    "cli.error": "error on {name}: {message}",
    "cli.summary": "error summary:",
    "cli.cancelled": "cancelled",
}
