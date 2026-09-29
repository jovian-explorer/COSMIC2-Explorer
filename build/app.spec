# -*- mode: python ; coding: utf-8 -*-
# COSMIC-2 Explorer - PyInstaller spec
# Updated 2026-09-20: complete VEDA hidden imports, offline assets, and application icon

import os
from pathlib import Path

block_cipher = None
spec_dir = Path(SPECPATH).resolve()
backend_dir = (spec_dir.parent / "backend").resolve()

a = Analysis(
    [str(backend_dir / "app.py")],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[
        (str(spec_dir.parent / "frontend"), "frontend"),
        (str(spec_dir.parent / "sampledata"), "sampledata"),
    ],
    hiddenimports=[
        # Scientific stack
        "netCDF4", "scipy", "scipy.signal", "scipy.ndimage",
        "matplotlib", "matplotlib.backends.backend_agg",
        # FastAPI / ASGI
        "fastapi", "uvicorn", "uvicorn.lifespan.on",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.logging",
        "starlette", "starlette.routing", "starlette.staticfiles",
        "anyio", "anyio._backends._asyncio",
        # pywebview + pythonnet
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "webview.util",
        "webview.guilib",
        "clr",
        "clr_loader",
        "pythonnet",
        # stdlib helpers that uvicorn/fastapi use dynamically
        "email.mime.multipart", "email.mime.base", "email.mime.text",
        "multipart",
        # VEDA planetary occultation packages
        "veda",
        "veda.api",
        "veda.api.routes",
        "veda.core",
        "veda.core.models",
        "veda.core.registry",
        "veda.core.base_adapter",
        "veda.analysis",
        "veda.analysis.atmospheric",
        "veda.missions",
        "veda.missions.manager",
        "veda.missions.cosmic2_adapter",
        "veda.missions.akatsuki_adapter",
        "veda.missions.bepicolombo_adapter",
        "veda.missions.cassini_adapter",
        "veda.missions.galileo_adapter",
        "veda.missions.juno_adapter",
        "veda.missions.maven_adapter",
        "veda.missions.new_horizons_adapter",
        "veda.missions.vex_adapter",
        "veda.readers",
        "veda.readers.fits_reader",
        "veda.readers.pds3_reader",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="COSMIC2-Explorer",
    icon=str(spec_dir / "cosmic2.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False -> windowed/GUI-only mode (no terminal window on launch).
    # disable_windowed_traceback=False keeps the PyInstaller crash handler active
    # so unhandled exceptions produce a dialog rather than silently vanishing.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
