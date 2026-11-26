# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: un solo spec per le tre build (BUILD_SPEC §9).

    pyinstaller packaging/stemforge.spec --noconfirm

Variabili d'ambiente (le imposta la CI, §9.6):
- STEMFORGE_TARGET_ARCH   macOS: x86_64 | arm64 (default: quella della macchina)
- STEMFORGE_MACOS_MIN     macOS: LSMinimumSystemVersion (10.15 Intel, 11.0 arm64)
- STEMFORGE_CODESIGN_IDENTITY  macOS: "-" = firma ad-hoc (default); una
  Developer ID per la distribuzione la applica packaging/notarize.sh

Note non ovvie:
- demucs legge remote/files.txt e i .yaml dei modelli: sono DATI, non
  moduli; senza collect_data_files l'app muore al primo caricamento
  (guasto visto sul campo, 12-08-2026).
- demucs ricostruisce le classi dei modelli via importlib leggendo i
  checkpoint: l'analisi statica non le vede, servono i collect_submodules.
- i pesi NON stanno nel bundle: si scaricano al primo avvio (§9.2).
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH)
ROOT = SPEC_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
from stemforge import __version__  # noqa: E402

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
ICON = str(SPEC_DIR / "icon.png")  # convertita in .icns/.ico da Pillow
AUDIO_EXTENSIONS = ["wav", "mp3", "flac", "ogg", "m4a", "aiff", "aif"]


def _windows_version_file() -> str:
    """Risorsa di versione dell'exe: nome e versione in Proprietà > Dettagli."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )

    numbers = tuple(int(p) for p in (__version__.split(".") + ["0", "0", "0"])[:4])
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


a = Analysis(
    [str(ROOT / "src" / "stemforge" / "ui" / "app.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=collect_data_files("demucs"),
    hiddenimports=[
        "stemforge.worker.runner",
        "stemforge.worker.selftest",
        "stemforge.engine.drumsplit",
        "stemforge.engine.vocalsplit",
        "stemforge.engine.dereverb",
        "soundfile",
        "av",
        *collect_submodules("demucs"),
        *collect_submodules("julius"),
        *collect_submodules("openunmix"),
        *collect_submodules("einops"),
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
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
    target_arch=os.environ.get("STEMFORGE_TARGET_ARCH") if IS_MAC else None,
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
            "LSMinimumSystemVersion": os.environ.get("STEMFORGE_MACOS_MIN", "10.15"),
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
