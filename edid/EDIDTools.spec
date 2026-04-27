# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules


project_dir = Path(SPECPATH)
src_dir = project_dir / "src"
sys.path.insert(0, str(src_dir))

datas = [
    (str(project_dir / "xml"), "xml"),
]

hiddenimports = collect_submodules("edid") + [
    "edid.ui.advancededideditordialog",
    "edid.ui.decodedediddialog",
    "edid.ui.edidcreationwizard",
    "edid.ui.mainwindow",
    "edid.ui.monitormanagersection",
    "edid.ui.rawblockeditordialog",
]

a = Analysis(
    ["edid_tools.py"],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EDIDTools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    name="EDIDTools",
)
