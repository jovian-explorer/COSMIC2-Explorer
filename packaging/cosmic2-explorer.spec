# -*- mode: python ; coding: utf-8 -*-
# COSMIC-2 Explorer: PyInstaller spec for Windows, macOS and Linux.
# Build with:  python scripts/build_exe.py
#
#   Windows  dist/COSMIC2-Explorer.exe      single file, no console
#   Linux    dist/COSMIC2-Explorer          single file
#   macOS    dist/COSMIC2-Explorer.app      app bundle

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
PKG = ROOT / "src" / "cosmic2"
ASSETS = PKG / "frontend" / "assets"
NAME = "COSMIC2-Explorer"

hiddenimports = collect_submodules("cosmic2") + [
    "netCDF4", "scipy.signal", "scipy.ndimage",
    "matplotlib.backends.backend_agg",
    "uvicorn.lifespan.on",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.logging",
    "anyio._backends._asyncio",
    "webview",
]
if sys.platform == "win32":
    hiddenimports += ["webview.platforms.edgechromium", "webview.platforms.winforms",
                      "clr", "clr_loader", "pythonnet"]
elif sys.platform == "darwin":
    hiddenimports += ["webview.platforms.cocoa"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(PKG / "frontend"), "cosmic2/frontend"),
        (str(PKG / "sampledata"), "cosmic2/sampledata"),
    ],
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME,
              console=False, upx=False, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=str(ASSETS / "cosmic2_icon.png"),
        bundle_identifier="io.github.jovian-explorer.cosmic2-explorer",
        info_plist={"NSHighResolutionCapable": True},
    )
else:
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=NAME,
        icon=str(ASSETS / "cosmic2.ico") if sys.platform == "win32" else None,
        # No console window; disable_windowed_traceback=False keeps PyInstaller's
        # crash dialog so an unhandled exception is never silent.
        console=False,
        disable_windowed_traceback=False,
        upx=True,
    )
