# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: un solo spec per i quattro profili (BUILD_SPEC §2, §9.1).

    pyinstaller packaging/stemforge.spec --noconfirm

Variabili d'ambiente (le imposta la CI, §9.6; senza, valgono i default):
- STEMFORGE_PROFILE    legacy-intel | mac-arm64 | win-x64 | linux-x64.
  Default: dedotto dal sistema (sul Mac dall'architettura del Python che
  esegue la build). Dal profilo discendono architettura e macOS minimo
  del Mac e quale FFmpeg LGPL entra nel pacchetto.
- STEMFORGE_TARGET_ARCH   macOS: se impostata deve coincidere col profilo
  (x86_64 per legacy-intel, arm64 per mac-arm64): un DMG etichettato
  arm64 con dentro un binario Intel sarebbe un inganno, non un'opzione.
- STEMFORGE_MACOS_MIN     macOS: sovrascrive LSMinimumSystemVersion.
- STEMFORGE_CODESIGN_IDENTITY  macOS: "-" = firma ad-hoc (default, la
  stessa provata sul campo); la Developer ID la applica notarize.sh.
- STEMFORGE_REQUIRE_FFMPEG=1  la build FALLISCE se manca il FFmpeg del
  profilo (la release lo imposta); senza, avvisa e prosegue: l'app
  funziona ma non legge m4a/aac/alac.

Note non ovvie:
- demucs legge remote/files.txt e i .yaml dei modelli: sono DATI, non
  moduli; senza collect_data_files l'app muore al primo caricamento
  (guasto visto sul campo, 12-08-2026).
- demucs ricostruisce le classi dei modelli via importlib leggendo i
  checkpoint: l'analisi statica non le vede, servono i collect_submodules.
- FFmpeg (D9) entra come BINARIO in "ffmpeg/": PyInstaller lo rende
  eseguibile e sul Mac lo firma insieme al resto; engine/ffmpeg.py lo
  cerca in sys._MEIPASS/ffmpeg/.
- i pesi NON stanno nel bundle: si scaricano al primo avvio (§9.2).
"""

import os
import platform
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
from stemforge import __version__  # noqa: E402

# profilo -> (sys.platform richiesto, architettura Mac, macOS minimo)
PROFILES = {
    "legacy-intel": ("darwin", "x86_64", "10.15"),
    "mac-arm64": ("darwin", "arm64", "11.0"),
    "win-x64": ("win32", None, None),
    "linux-x64": ("linux", None, None),
}
_X64_MACHINES = ("x86_64", "amd64")
_TRUTHY = ("1", "true", "yes")
AUDIO_EXTENSIONS = ["wav", "mp3", "flac", "ogg", "m4a", "aiff", "aif"]


def _fail(message):
    raise SystemExit(f"\nERRORE stemforge.spec: {message}\n")


def _warn(message):
    # print e non logger: l'installer del Mac gira con --log-level ERROR e
    # questo avviso deve arrivare comunque all'utente
    print(f"\nATTENZIONE stemforge.spec: {message}\n", file=sys.stderr)


def _default_profile():
    if sys.platform == "darwin":
        arch = os.environ.get("STEMFORGE_TARGET_ARCH") or platform.machine()
        return "mac-arm64" if arch == "arm64" else "legacy-intel"
    return "win-x64" if sys.platform == "win32" else "linux-x64"


def _resolve_profile():
    profile = os.environ.get("STEMFORGE_PROFILE") or _default_profile()
    if profile not in PROFILES:
        _fail(f"STEMFORGE_PROFILE={profile!r} non valido; ammessi: {', '.join(PROFILES)}")
    wanted_platform, mac_arch, _ = PROFILES[profile]
    if sys.platform != wanted_platform:
        _fail(f"il profilo {profile} si costruisce su {wanted_platform}, non su {sys.platform}")
    requested_arch = os.environ.get("STEMFORGE_TARGET_ARCH")
    if mac_arch and requested_arch and requested_arch != mac_arch:
        _fail(f"STEMFORGE_TARGET_ARCH={requested_arch} contraddice il profilo {profile} ({mac_arch})")
    # niente build incrociate: torch esiste per una sola architettura per
    # wheel, quindi il Python che costruisce deve gia' essere quello giusto
    machine = platform.machine().lower()
    if mac_arch and machine != mac_arch:
        _fail(f"il profilo {profile} va costruito con un Python {mac_arch}, questo e' {machine}"
              + (" (su Apple Silicon: arch -x86_64)" if mac_arch == "x86_64" else ""))
    if mac_arch is None and machine not in _X64_MACHINES:
        _fail(f"il profilo {profile} e' x64, questa macchina e' {platform.machine()}")
    return profile


def _ffmpeg_binaries(profile):
    """Il FFmpeg LGPL del profilo (area packaging/ffmpeg/, D9), se c'e'."""
    name = "ffmpeg.exe" if profile == "win-x64" else "ffmpeg"
    path = SPEC_DIR / "ffmpeg" / "out" / profile / name
    if path.is_file():
        print(f"stemforge.spec: FFmpeg LGPL incluso: {path}")
        return [(str(path), "ffmpeg")]
    missing = f"FFmpeg LGPL del profilo {profile} non trovato in {path}"
    if os.environ.get("STEMFORGE_REQUIRE_FFMPEG", "").strip().lower() in _TRUTHY:
        _fail(f"{missing}.\nCompilalo prima (packaging/ffmpeg/, BUILD_SPEC D9) oppure "
              "togli STEMFORGE_REQUIRE_FFMPEG per una build senza m4a/aac.")
    _warn(f"{missing}.\nProseguo: l'app funzionera' ma NON aprira' m4a/aac/alac.")
    return []


def _translations():
    """Le traduzioni compilate di Qt Linguist (§8.6) vanno in "i18n/"."""
    found = sorted((ROOT / "resources" / "i18n").glob("*.qm"))
    if not found:
        _warn("nessuna traduzione .qm in resources/i18n: l'interfaccia restera' "
              "nella lingua dei sorgenti.")
    return [(str(path), "i18n") for path in found]


def _icon():
    """icon.png convertita da Pillow in .icns/.ico; Linux non ha icona nell'eseguibile."""
    if sys.platform not in ("darwin", "win32"):
        return None
    try:
        import PIL  # noqa: F401
    except ImportError:
        _fail("serve Pillow per convertire icon.png in .icns/.ico: "
              "pip install -r packaging/requirements-build.txt")
    return str(SPEC_DIR / "icon.png")


def _windows_version_file():
    """Risorsa di versione dell'exe: nome e versione in Proprieta' > Dettagli."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )

    digits = [int(part) for part in re.findall(r"\d+", __version__)]
    numbers = tuple((digits + [0, 0, 0, 0])[:4])
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[
            StringFileInfo([StringTable("041004B0", [
                StringStruct("CompanyName", "StemForge"),
                StringStruct("FileDescription", "StemForge"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", "StemForge"),
                StringStruct("OriginalFilename", "StemForge.exe"),
                StringStruct("ProductName", "StemForge"),
                StringStruct("ProductVersion", __version__),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0410, 1200])]),
        ],
    )
    target = Path(workpath) / "version_info.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(info), encoding="utf-8")
    return str(target)


PROFILE = _resolve_profile()
_, MAC_ARCH, MAC_MIN = PROFILES[PROFILE]
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
ICON = _icon()
print(f"stemforge.spec: profilo {PROFILE}, StemForge {__version__}")

a = Analysis(
    [str(ROOT / "src" / "stemforge" / "ui" / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=_ffmpeg_binaries(PROFILE),
    datas=[*collect_data_files("demucs"), *_translations()],
    hiddenimports=[
        "stemforge.worker.runner",
        "stemforge.worker.selftest",
        "stemforge.engine.drumsplit",
        "stemforge.engine.vocalsplit",
        "stemforge.engine.dereverb",
        "soundfile",
        *collect_submodules("demucs"),
        *collect_submodules("julius"),
        *collect_submodules("openunmix"),
        *collect_submodules("einops"),
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # PyAV porta un FFmpeg GPLv3 (D9): non deve entrare nel pacchetto
        # nemmeno se e' rimasto installato nell'ambiente di build
        "av",
        # senza esclusioni il bundle passa abbondantemente 1 GB (§9.1)
        "matplotlib",
        "tkinter",
        "IPython",
        "pytest",
        "torch.utils.tensorboard",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtPdf",
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StemForge",
    console=False,
    icon=ICON,
    # i parametri seguenti PyInstaller li usa solo sul Mac: None altrove
    target_arch=MAC_ARCH,
    codesign_identity=os.environ.get("STEMFORGE_CODESIGN_IDENTITY", "-") if IS_MAC else None,
    entitlements_file=str(SPEC_DIR / "entitlements.plist") if IS_MAC else None,
    version=_windows_version_file() if IS_WIN else None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="StemForge")

if IS_MAC:
    app = BUNDLE(
        coll,
        name="StemForge.app",
        icon=ICON,
        bundle_identifier="com.stemforge.app",
        version=__version__,
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": os.environ.get("STEMFORGE_MACOS_MIN") or MAC_MIN,
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.music",
            # "Apri con" dal Finder (§9.1)
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Audio",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "LSItemContentTypes": ["public.audio"],
                    "CFBundleTypeExtensions": AUDIO_EXTENSIONS,
                }
            ],
        },
    )
