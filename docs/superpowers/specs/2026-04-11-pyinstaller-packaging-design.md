# PyInstaller Packaging & CI Release — Spec

**Date:** 2026-04-11  
**Status:** Approved

## Goal

Package SoilSight as a native installer for Mac (`.dmg`) and Windows (`.exe`) using PyInstaller, with GitHub Actions CI publishing both installers as release assets when a version tag is pushed.

## Approach

PyInstaller + `create-dmg` (Mac) + NSIS (Windows), triggered via GitHub Actions matrix on `v*` tags.

---

## 1. PyInstaller Spec File

**File:** `SoilSight.spec` (project root)

### Data files bundled

| Source | Destination in bundle |
|---|---|
| `mpcamera/layouts/*.ui` | `mpcamera/layouts/` |
| `mpcamera/assets/*` | `mpcamera/assets/` |
| `mpcamera/config_schema.json` | `mpcamera/` |

### Hidden imports

```
cv2, PyQt6, PyQt6.QtCore, PyQt6.QtGui, PyQt6.QtWidgets,
torch, torchvision, ultralytics, rfdetr, inference_sdk,
sklearn, sklearn.utils._cython_blas, sklearn.neighbors._typedefs,
dotenv
```

### Exclusions

- `models/` — users copy weights manually after install
- `.env` — users configure via Settings UI; config synced to `~/.mpcamera/config.json`

### Output

- Folder bundle: `dist/SoilSight/` (both platforms)
- `console=False` (no terminal window)
- Icon: `mpcamera/assets/SoilSight_Logo.ico`

---

## 2. Platform Build Scripts

### Mac — `build/build_mac.sh`

1. Activate `.venv311`
2. `pip install pyinstaller create-dmg` (if not already installed)
3. `pyinstaller SoilSight.spec --clean`
4. `create-dmg` wraps `dist/SoilSight.app` into `dist/SoilSight-<VERSION>-mac.dmg`
   - Includes drag-to-Applications shortcut
   - Window size: 660×400, icon size: 100px

### Windows — `build/build_win.ps1`

1. Activate `.venv311`
2. `pip install pyinstaller`
3. `pyinstaller SoilSight.spec --clean`
4. `makensis build/installer.nsi` produces `dist/SoilSight-<VERSION>-windows-setup.exe`

### NSIS script — `build/installer.nsi`

- Install to `$PROGRAMFILES\SoilSight`
- Create Start Menu shortcut
- Create uninstaller (`Uninstall SoilSight`)
- Reads version from `VERSION` file

---

## 3. Version File

**File:** `VERSION` (project root, plain text, e.g. `1.0.0`)

Both build scripts and the GitHub Actions workflow read from this file. Bump it before tagging a release.

---

## 4. GitHub Actions Workflow

**File:** `.github/workflows/build-release.yml`

**Trigger:** Push tag matching `v*`

**Matrix:** `[macos-latest, windows-latest]` (parallel jobs)

**Each job:**
1. `actions/checkout@v4`
2. `actions/setup-python@v5` with Python 3.11
3. `pip install -r requirements.txt pyinstaller`
4. Install platform tooling (create-dmg on Mac, NSIS on Windows via chocolatey)
5. Run platform build script
6. `softwareupdate --install-rosetta` not needed (macos-latest is now Apple Silicon)
7. Upload artifact to GitHub Release via `softprops/action-gh-release`

**Release assets produced:**
- `SoilSight-<version>-mac.dmg`
- `SoilSight-<version>-windows-setup.exe`

---

## 5. What Is NOT Included

- Code signing / notarization (can be added later)
- Auto-update mechanism
- Linux packaging
- `models/` directory — users manually place `.pth`/`.pt` weights in the installed app's `models/` folder
