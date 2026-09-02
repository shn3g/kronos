# SPDX-License-Identifier: AGPL-3.0-or-later
"""PyInstaller onedir spec for the Kronos engine sidecar."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

engine_root = Path(SPECPATH)
src = engine_root / "src"

hiddenimports = [
    "kronos_engine",
    *collect_submodules("kronos_engine"),
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "starlette.routing",
    "pydantic",
    "pydantic.deprecated.decorator",
    "cryptography",
    "keyring",
    "keyring.backends",
    "watchfiles",
    "httpx",
    "httpx._transports",
    "httpx._transports.default",
    "onnxruntime",
    "tokenizers",
    "numpy",
    "sqlite3",
    "multiprocessing",
]

if sys.platform == "win32":
    hiddenimports.extend(collect_submodules("winpty"))

a = Analysis(
    [str(src / "kronos_engine" / "main.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="kronos-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="kronos-engine",
)
