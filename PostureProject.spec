# -*- mode: python ; coding: utf-8 -*-
#
# PostureProject.spec
# -------------------
# PyInstaller spec for building PostureProject.exe (Windows, onedir, no console).
#
# Build with:
#   py -3.11-64 -m PyInstaller PostureProject.spec --noconfirm
#
# Output: dist\PostureProject\PostureProject.exe
#   Copy the entire dist\PostureProject\ folder to run on other machines.

from PyInstaller.utils.hooks import collect_all, collect_data_files

# mediapipe uses dynamic imports and ships native DLLs — collect everything
mp_datas, mp_binaries, mp_hiddenimports = collect_all("mediapipe")

# google.protobuf also uses dynamic class loading
proto_datas, proto_binaries, proto_hiddenimports = collect_all("google.protobuf")

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[
        *mp_binaries,
        *proto_binaries,
    ],
    datas=[
        # Bundled model asset — goes to sys._MEIPASS root
        ("pose_landmarker_lite.task", "."),
        *mp_datas,
        *proto_datas,
    ],
    hiddenimports=[
        *mp_hiddenimports,
        *proto_hiddenimports,
        # tkinter is sometimes missed on Windows
        "tkinter",
        "tkinter.font",
        # winsound is stdlib but occasionally needs explicit inclusion
        "winsound",
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages to keep bundle smaller
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PostureProject",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt mediapipe DLLs — keep off
    console=False,      # No terminal window (windowed app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # TODO: add icon.ico here once available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PostureProject",
)
