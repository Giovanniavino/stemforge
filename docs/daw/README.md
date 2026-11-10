# Consegna alle DAW — sintesi della ricerca

Questa cartella documenta come StemForge consegna gli stem alle DAW con il
drag & drop (BUILD_SPEC §7.1, §7.2, §7.2.1) e come si collauda a mano.

- `README.md` — questo file: cosa leggono le DAW, cosa produce Qt, perché
  `ui/drag_export.py` è fatto così, con le fonti.
- [`checklist.md`](checklist.md) — il collaudo manuale DAW × sistema,
  dieci minuti per DAW.

## In una riga

Il drag porta **un solo formato MIME, `text/uri-list`**, con gli URL
`file://` dei file già chiusi. Qt lo traduce nel formato nativo di ogni
sistema (`CF_HDROP` su Windows, un `public.file-url` per file su macOS,
`text/uri-list` XDND su Linux), che è lo stesso che producono Esplora
file, il Finder e i file manager: le DAW lo leggono senza codice specifico.

## Cosa produce Qt (letto nel sorgente 6.4.3 e 6.7.3, verificato dove si può)

### Windows

- `QWindowsMimeURI` (in `qwindowsmime.cpp` fino a 6.4, in
  `qwindowsmimeregistry.cpp` dal 6.5; codice equivalente) per
  `text/uri-list` offre `CF_HDROP` se almeno un URL è locale, più
  `UniformResourceLocatorW` e `UniformResourceLocator`. Il `CF_HDROP` è
  una `DROPFILES` con `fWide = true`: i percorsi viaggiano in UTF-16, uno
  per file, ricavati con `QDir::toNativeSeparators(url.toLocalFile())`.
  Qt **non** produce `FileName`, `FileNameW` né `Shell IDList Array`.
- Nel **drag** l'oggetto OLE è un `QWindowsDropDataObject`: se il
  QMimeData ha *un solo* formato, contiene URL e sono tutti file locali,
  `GetData`/`QueryGetData` rifiutano `CF_TEXT`, `CF_UNICODETEXT` e
  `UniformResourceLocator(W)` (`shouldIgnore`). Il bersaglio vede solo i
  file, non un link né un testo: è la correzione di QTBUG-62662 (Outlook
  creava un collegamento invece di un allegato). **Per questo
  `drag_export` non aggiunge altri formati MIME**: il secondo formato
  spegnerebbe quel filtro.
- **Verificato eseguendo** sul dev-box Windows 11 con PySide6 6.7.3 e
  6.4.3 (`tests/integration/test_daw_clipboard.py`): il QMimeData di
  `build_mime_data` messo negli appunti (stesso convertitore, ma oggetto
  `QWindowsOleDataObject`, quindi senza il filtro del drag) espone i
  formati `CF_HDROP` (15), `UniformResourceLocator`,
  `UniformResourceLocatorW`, `DataObject`, `Ole Private Data`; e
  `DragQueryFileW` sul `CF_HDROP` restituisce esattamente i percorsi,
  con spazi, accenti, ideogrammi, `#`, `%`, `[ ]`, e per un percorso
  oltre `MAX_PATH` la forma 8.3 delle cartelle senza prefisso `\\?\`.
  Il drag OLE vero (`DoDragDrop`) non si può automatizzare qui: il filtro
  di `shouldIgnore` è verificato solo leggendo il sorgente.

### macOS

- `QCocoaDrag::maybeDragMultipleItems`: con **più di un URL** (e macOS ≥
  10.14) Qt crea un `NSDraggingItem` per URL con l'`NSURL` come
  pasteboard writer — come il Finder. Con un solo URL usa `dragImage:` e
  il convertitore `QMacPasteboardMimeFileUri` scrive `public.file-url`
  (che dichiara `count() == urls().count()`, un elemento per file).
- Qt non scrive il vecchio `NSFilenamesPboardType`; le app che lo leggono
  ancora dipendono dalla traduzione di AppKit. Non verificabile da
  Windows: è una riga della checklist (Logic, Cubase, Studio One).
- Modificatori: AppKit, se l'utente tiene Cmd, Ctrl o Opzione, riduce la
  maschera delle operazioni della sorgente (con Cmd resterebbe solo
  "Generic", che con il nostro solo Copy darebbe una maschera vuota). Qt
  risponde `YES` a `ignoreModifierKeysForDraggingSession:`
  (`qnsview_dragging.mm`) e restituisce sempre la maschera delle azioni
  del QDrag: un Cmd-drag, che Ableton usa per "un file per traccia",
  resta un Copy. Letto nel sorgente, da provare (checklist C6).

### Linux (X11)

- `QXcbMime::mimeAtomsForFormat`: per `text/uri-list` Qt offre gli atomi
  `text/uri-list`, `text/x-moz-url` (solo il primo URL, UTF-16) e
  `text/plain`.
- `drag_export` scrive il payload `text/uri-list` **esplicito**: un URI
  `file://` per riga, CRLF (RFC 2483), path codificato come
  `g_filename_to_uri` di GLib (tutto tranne unreserved e `/`). Qt da sé
  lascerebbe `[` e `]` nudi nel path, che RFC 3986 non ammette.
- REAPER su Linux usa SWELL su GDK: al drop chiede l'atomo
  `text/uri-list`, tiene solo le righe che iniziano con `file://`,
  decodifica i `%XX` e consegna una `DROPFILES` all'app
  (`swell-generic-gdk.cpp`, `urilistToDropFiles`). Il parser si ferma al
  primo spazio bianco e non conosce un host dopo `file://`: per questo
  gli spazi devono arrivare come `%20` e l'URI è `file:///percorso`,
  senza `localhost`. Il nostro payload è esattamente quello.
- Wayland: Qt offre gli stessi tipi MIME via `wl_data_source`; il ponte
  verso app XWayland lo fa il compositor. Da provare (checklist).

## Cosa leggono le DAW

| DAW | Sistemi | Cosa legge al drop di file | Fonte / confidenza |
|---|---|---|---|
| Ableton Live | mac, win | file da Explorer/Finder ("Files can also be dropped directly into Live"); drop sotto le tracce = traccia nuova. Più file: il manuale 12 non dice nulla; secondo il forum senza modificatori vanno in sequenza su una traccia, con Ctrl/Cmd una traccia per file | manuale ufficiale (cap. 4.10); il modificatore solo da forum (2007–2009), da verificare (checklist C2) |
| Logic Pro | mac | file URL dal Finder; più file → dialogo "Add Selected Files to Tracks" | Apple, guida di Logic; il nome del dialogo da manuali vecchi e forum |
| FL Studio | mac, win | file da Explorer/Finder su Playlist, Channel rack, Browser | Image-Line KB 571 (non in Fruity Edition sulla Playlist) |
| REAPER | mac, win, linux | `CF_HDROP` su Windows; `text/uri-list` su Linux (SWELL, sorgente letto); più file → domanda "una traccia per file?" | sorgente WDL/SWELL, reaper.blog, CockosWiki |
| Cubase | mac, win | file da Explorer/Finder; più file → dialogo Import Options "Different Tracks / One Track" | Steinberg help; regressione segnalata in 15.0.20 |
| Studio One (Fender Studio Pro) | mac, win | file da Explorer/Finder nell'Arrange | manuale (Files tab); comportamento multi-file non documentato |
| Bitwig Studio | mac, win, linux | file da file manager nell'Arranger / Clip Launcher; modificatori per stretch / raw (5.2+) | guida utente; multi-file non documentato |

Le sorgenti di drag più diffuse verso le DAW sono i sample manager e i
plugin fatti con **JUCE**, che su Windows offrono **solo `CF_HDROP`**
(`performExternalDragDropOfFiles`, `DROPEFFECT_COPY`) e come bersaglio
leggono prima `CF_HDROP` (con `DragQueryFile`) e poi `CF_UNICODETEXT`.
Se `CF_HDROP` da solo basta a quelle app con tutte le DAW, basta anche a
noi: **nessun formato Windows aggiuntivo è dimostrato necessario**, quindi
non se ne aggiungono (la spec chiede di aggiungerli solo se servono).

## Problemi noti (non risolvibili dal nostro lato)

- **Windows, DAW elevata**: se la DAW gira come amministratore, UIPI
  blocca il drag & drop da un processo non elevato — anche da Esplora
  file. Sintomo: cursore "divieto". Rimedio: avviare la DAW senza
  privilegi elevati (Image-Line KB 571; Microsoft, MIC e UIPI).
- **Warp / stretch automatici**: Ableton (Auto-Warp per i campioni lunghi),
  Bitwig (stretch al tempo del progetto) e altre possono stirare ciascun
  file per conto suo: gli stem si disallineano anche se il file è giusto.
  La checklist chiede di controllare l'allineamento e di annotare
  l'impostazione.
- **Frequenza di campionamento** diversa dal progetto: Cubase e Logic
  chiedono se convertire; non è un difetto del drag.
- **Flatpak su Linux** (es. Bitwig da Flathub): la DAW vede il file solo
  se il sandbox ha accesso alla cartella di output.
- Una DAW che ricava l'azione dal drop e accetta solo Move rifiuterebbe il
  drop: StemForge offre solo Copy (§7.2). Nessuna delle DAW elencate è
  documentata così; la checklist lo intercetta (cursore "divieto").

## Fonti

Qt (sorgente, tag v6.4.3 e v6.7.3):
- https://github.com/qt/qtbase/blob/v6.4.3/src/plugins/platforms/windows/qwindowsmime.cpp
- https://github.com/qt/qtbase/blob/v6.7.3/src/plugins/platforms/windows/qwindowsmimeregistry.cpp
- https://github.com/qt/qtbase/blob/v6.4.3/src/plugins/platforms/windows/qwindowsdropdataobject.cpp
- https://github.com/qt/qtbase/blob/v6.7.3/src/plugins/platforms/windows/qwindowsdropdataobject.cpp
- https://github.com/qt/qtbase/blob/v6.4.3/src/plugins/platforms/cocoa/qcocoadrag.mm
- https://github.com/qt/qtbase/blob/v6.4.3/src/plugins/platforms/cocoa/qnsview_dragging.mm
- https://github.com/qt/qtbase/blob/v6.4.3/src/gui/platform/darwin/qmacmime.mm
- https://github.com/qt/qtbase/blob/v6.4.3/src/plugins/platforms/xcb/qxcbmime.cpp
- https://github.com/qt/qtbase/blob/v6.4.3/src/corelib/kernel/qmimedata.cpp
- QTBUG-62662 (drag di file locali verso Outlook): https://bugreports.qt.io/browse/QTBUG-62662
- Storia di qwindowsdropdataobject.cpp: https://code.qt.io/cgit/qt/qtbase.git/log/src/plugins/platforms/windows/qwindowsdropdataobject.cpp?showmsg=1

JUCE e REAPER/SWELL:
- https://github.com/juce-framework/JUCE/blob/master/modules/juce_gui_basics/native/juce_DragAndDrop_windows.cpp
- https://github.com/juce-framework/JUCE/blob/master/modules/juce_gui_basics/native/juce_Windowing_windows.cpp
- https://github.com/justinfrankel/WDL/blob/main/WDL/swell/swell-generic-gdk.cpp

DAW:
- Ableton Live 12, Working with the Browser: https://www.ableton.com/en/live-manual/12/working-with-the-browser/
- Ableton forum, più file su tracce separate (Ctrl/Cmd): https://forum.ableton.com/viewtopic.php?p=911794
- Logic Pro, creare tracce trascinando file: https://support.apple.com/guide/logicpro/lgcp8a38436c/mac
- Logic Pro, drag & drop per tracce Sampler: https://support.apple.com/101863
- Image-Line KB 571 (drag & drop, privilegi di amministratore, Fruity Edition): https://support.image-line.com/action/knowledgebase?ans=571
- REAPER 101, importare più file: https://reaper.blog/2012/08/reaper-101-importing-multiple-audio-files/
- CockosWiki, Media preferences ("When inserting multiple media items"): https://www.cockos.com/wiki/index.php/Preferences_Media_Preferences
- Steinberg, Adding Tracks by Dragging Files (Import Options): https://steinberg.help/nuendo/v12/en/cubase_nuendo/topics/track_handling/track_handling_tracks_by_dragging_files_from_the_mediabay_adding_t.html
- Steinberg forum, dialogo "One Track / Different Tracks" sparito in 15.0.20: https://forums.steinberg.net/t/15-0-20-one-track-different-track-dialog-missing/1029082
- Fender Studio Pro (ex Studio One), Files tab: https://fenderstudiopromanual.fender.com/en/Content/The_Browser_Topics/Files_Tab.htm
- Bitwig Studio, Arranger Clips and the Browser Panel: https://www.bitwig.com/userguide/latest/arranger_clips_and_the_browser_panel

Windows:
- Microsoft, perché il drag & drop non funziona verso un'app elevata (MIC e UIPI): https://learn.microsoft.com/en-us/archive/blogs/patricka/q-why-doesnt-drag-and-drop-work-when-my-application-is-running-elevated-a-mandatory-integrity-control-and-uipi
- RFC 2483 (text/uri-list): https://www.rfc-editor.org/rfc/rfc2483
- RFC 3986 (sintassi URI): https://www.rfc-editor.org/rfc/rfc3986
