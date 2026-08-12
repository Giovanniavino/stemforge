# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec per il target Mac Intel (BUILD_SPEC §9.1).

Da eseguire SUL MAC: pyinstaller packaging/stemforge.spec
- target_arch x86_64: il target è il Mac Intel (§9.1).
- niente --deep in codesign: l'identità si passa qui e PyInstaller firma
  la gerarchia dall'interno verso l'esterno (§9.3). "-" = ad-hoc.
- i pesi NON sono nel bundle: si scaricano al primo avvio (§9.2).
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

CODESIGN_IDENTITY = os.environ.get("STEMFORGE_CODESIGN_IDENTITY", "-")

block_cipher = None

a = Analysis(
    ["../src/stemforge/ui/app.py"],
    pathex=["../src"],
    binaries=[],
    # demucs/remote/files.txt e i .yaml: l'indice dei modelli con i
    # checksum. Senza, get_model() muore con FileNotFoundError prima
    # ancora di provare a scaricare (visto sul campo, log 12-08-2026).
    datas=collect_data_files("demucs"),
    hiddenimports=[
        "stemforge.worker.runner",
        "soundfile",
        # demucs carica le classi dei modelli via importlib leggendo i
        # metadati del checkpoint: l'analisi statica non le vede e senza
        # di queste il worker muore al caricamento dei pesi
        *collect_submodules("demucs"),
        *collect_submodules("julius"),
        *collect_submodules("openunmix"),
        *collect_submodules("einops"),
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # senza esclusioni il bundle passa 1 GB (§9.1)
        "matplotlib",
        "tkinter",
        "IPython",
        "pytest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtPdf",
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StemForge",
    console=False,
    target_arch="x86_64",
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file="entitlements.plist",
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="StemForge")

AUDIO_EXTENSIONS = ["wav", "mp3", "flac", "ogg", "m4a", "aiff", "aif"]

app = BUNDLE(
    coll,
    name="StemForge.app",
    icon=None,
    bundle_identifier="com.stemforge.app",
    info_plist={
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
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
