# Build with:
# pyinstaller ISUZUOfferGenerator.spec
from pathlib import Path
import sys

block_cipher = None


def python_runtime_binaries():
    candidates = []
    for base in {Path(sys.executable).resolve().parent, Path(sys.base_prefix), Path(sys.exec_prefix)}:
        for name in (
            f"python{sys.version_info.major}{sys.version_info.minor}.dll",
            f"python{sys.version_info.major}.dll",
        ):
            path = base / name
            if path.exists():
                candidates.append((str(path), "."))
    return list(dict.fromkeys(candidates))


a = Analysis(
    ["desktop_launcher.py"],
    pathex=[],
    binaries=python_runtime_binaries(),
    datas=[
        ("app/templates", "app/templates"),
        ("app/static", "app/static"),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.off",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "clr",
        "clr_loader",
        "pythonnet",
        "webview",
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
    name="ISUZU_Offer_App",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    upx=True,
    upx_exclude=[],
    name="ISUZU_Offer_App",
)
