# SoilSight.spec
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── Data files ──────────────────────────────────────────────────────────────
datas = [
    ("mpcamera/layouts/*.ui",     "mpcamera/layouts"),
    ("mpcamera/assets",           "mpcamera/assets"),
    ("mpcamera/config_schema.json", "mpcamera"),
]

# Collect all data/binaries from heavy packages
for pkg in ("torch", "torchvision", "ultralytics", "cv2", "rfdetr", "inference_sdk", "supervision"):
    d, b, h = collect_all(pkg)
    datas     += d

# sklearn data files
datas += collect_data_files("sklearn")

# ── Hidden imports ───────────────────────────────────────────────────────────
hiddenimports = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "cv2",
    "torch",
    "torchvision",
    "ultralytics",
    "rfdetr",
    "inference_sdk",
    "supervision",
    "sklearn",
    "sklearn.utils._cython_blas",
    "sklearn.neighbors._typedefs",
    "sklearn.tree._utils",
    "dotenv",
    "PIL",
    "PIL.Image",
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["models"],
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
    name="SoilSight",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="mpcamera/assets/SoilSight_Logo.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SoilSight",
)

# Mac: wrap as .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="SoilSight.app",
        icon="mpcamera/assets/SoilSight_Logo.ico",
        bundle_identifier="com.soilsight.app",
        info_plist={
            "NSPrincipalClass": "NSApplication",
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": Path("VERSION").read_text().strip(),
            "NSCameraUsageDescription": "SoilSight needs camera access to capture microscope frames for microplastic analysis.",
        },
    )
