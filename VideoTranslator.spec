# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for VideoTranslator (single-file exe)."""

import os

from PyInstaller.utils.hooks import collect_all

# Packages that ship data files / native libraries and need explicit collection.
PACKAGES = [
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "tokenizers",
    "huggingface_hub",
    "hf_xet",
    "fugashi",
    "unidic_lite",
    "imageio_ffmpeg",
    "customtkinter",
    "darkdetect",
]

datas = []
binaries = []
hiddenimports = []
for package in PACKAGES:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hidden)

# Offline dictionaries: compact curated list + full JMdict with Russian glosses.
datas.append(("dict/ja_en_mini.json", "dict"))
datas.append(("dict/jmdict_ru_common.json", "dict"))
datas.append(("dict/warodai_txt.zip", "dict"))

hiddenimports.extend(
    [
        "tkinter",
        "core.audio",
        "core.dictionary",
        "core.pipeline",
        "core.subtitles",
        "core.transcribe",
        "core.translate",
    ]
)

a = Analysis(
    ["app.py"],
    pathex=[os.path.abspath(".")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VideoTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
