"""Le estensioni audio che il motore sa leggere (BUILD_SPEC §5.7, D9, §10.1).

Un modulo di soli dati, senza soundfile né numpy: lo importa anche il
processo dell'interfaccia (worker/planning.py, per rifiutare al drop
ESATTAMENTE ciò che il caricamento non saprebbe leggere), che non deve
caricare le librerie di decodifica (§8.5). La decodifica sta in decode.py.
"""

from __future__ import annotations

# Letti da libsndfile: se soundfile fallisce su questi, il file è rotto.
SOUNDFILE_EXTENSIONS = frozenset(
    {".wav", ".wave", ".flac", ".ogg", ".oga", ".mp3", ".aiff", ".aif", ".aifc"}
)
# Solo FFmpeg: m4a porta AAC o ALAC, .aac è AAC grezzo (ADTS).
FFMPEG_EXTENSIONS = frozenset({".m4a", ".aac"})
SUPPORTED_EXTENSIONS = SOUNDFILE_EXTENSIONS | FFMPEG_EXTENSIONS
