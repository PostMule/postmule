# -*- mode: python ; coding: utf-8 -*-
# PostMule PyInstaller spec
#
# Uses collect_submodules() so every module under postmule/providers/ is
# bundled automatically — no manual hidden-import list to maintain.
#
# Build: run installer/build.ps1 from the repo root.

import os
from PyInstaller.utils.hooks import collect_submodules

# Repo root is one level up from the installer/ directory where this spec lives.
repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))

hiddenimports = (
    collect_submodules("postmule.providers")
    + ["flask", "jinja2", "keyring.backends.Windows"]
)

datas = [
    (os.path.join(repo_root, "config.example.yaml"), "."),
    (os.path.join(repo_root, "postmule", "web", "templates"), "postmule/web/templates"),
    (os.path.join(repo_root, "postmule", "web", "static"),    "postmule/web/static"),
]

a = Analysis(
    [os.path.join(repo_root, "postmule", "cli.py")],
    pathex=[repo_root],
    binaries=[],
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
    [],
    exclude_binaries=True,
    name="postmule",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="postmule",
)
