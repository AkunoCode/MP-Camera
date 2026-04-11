# PyInstaller Packaging & CI Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package SoilSight as a native `.dmg` (Mac) and `.exe` installer (Windows) using PyInstaller, published automatically via GitHub Actions when a `v*` tag is pushed.

**Architecture:** A shared `SoilSight.spec` drives PyInstaller on both platforms. Platform-specific wrapper scripts produce a `.dmg` (Mac via `create-dmg`) and a `.exe` (Windows via NSIS). A GitHub Actions matrix workflow builds both in parallel and uploads them as release assets.

**Tech Stack:** PyInstaller, create-dmg, NSIS, GitHub Actions, PyQt6, torch, ultralytics

---

## File Map

| File | Action |
|---|---|
| `VERSION` | Create |
| `SoilSight.spec` | Create |
| `build/build_mac.sh` | Create |
| `build/build_win.ps1` | Create |
| `build/installer.nsi` | Create |
| `.github/workflows/build-release.yml` | Create |

---

### Task 1: Create VERSION file and install PyInstaller

**Files:**
- Create: `VERSION`

- [ ] **Step 1: Create the VERSION file**

```
1.0.0
```

Save as `VERSION` at the project root (no newline issues — just the version string on one line).

- [ ] **Step 2: Install PyInstaller into the venv**

```bash
cd /Users/kodecraft-carlo-rabe/Desktop/MP-Camera
source .venv311/bin/activate
pip install pyinstaller pyinstaller-hooks-contrib
```

Expected: installs without error. `pyinstaller --version` should print `6.x.x`.

- [ ] **Step 3: Verify PyInstaller can see the entry point**

```bash
source .venv311/bin/activate
python -c "import PyInstaller; print(PyInstaller.__version__)"
python -c "import main; print('entry point OK')"
```

Expected: both print without error.

- [ ] **Step 4: Commit**

```bash
git add VERSION
git commit -m "chore: add VERSION file for release tagging"
```

---

### Task 2: Create `SoilSight.spec`

**Files:**
- Create: `SoilSight.spec`

- [ ] **Step 1: Write the spec file**

```python
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
        },
    )
```

- [ ] **Step 2: Run a test build on Mac**

```bash
source .venv311/bin/activate
pyinstaller SoilSight.spec --clean 2>&1 | tail -30
```

Expected: ends with `Building BUNDLE SoilSight.app completed successfully.`

If you see `ModuleNotFoundError` for a package, add it to `hiddenimports`. If you see missing data files, add them to `datas`.

- [ ] **Step 3: Verify the .app launches**

```bash
open dist/SoilSight.app
```

Expected: SoilSight window opens. Check the Settings page loads and the tab layout is visible. Close the app.

- [ ] **Step 4: Commit**

```bash
git add SoilSight.spec
git commit -m "build: add PyInstaller spec for SoilSight"
```

---

### Task 3: Create Mac build script

**Files:**
- Create: `build/build_mac.sh`

- [ ] **Step 1: Create the build directory and script**

```bash
mkdir -p build
```

Write `build/build_mac.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Read version
VERSION=$(cat VERSION)
echo "Building SoilSight v$VERSION for macOS..."

# Activate venv
source .venv311/bin/activate

# Install build tools if not present
pip install pyinstaller pyinstaller-hooks-contrib --quiet
# create-dmg must be installed via Homebrew (the pip package is unrelated)
if ! command -v create-dmg &>/dev/null; then
  brew install create-dmg
fi

# Clean previous build
rm -rf dist/SoilSight.app dist/SoilSight build/

# Run PyInstaller
pyinstaller SoilSight.spec --clean

# Create .dmg
create-dmg \
  --volname "SoilSight $VERSION" \
  --volicon "mpcamera/assets/SoilSight_Logo.ico" \
  --window-pos 200 120 \
  --window-size 660 400 \
  --icon-size 100 \
  --icon "SoilSight.app" 165 185 \
  --hide-extension "SoilSight.app" \
  --app-drop-link 495 185 \
  "dist/SoilSight-${VERSION}-mac.dmg" \
  "dist/SoilSight.app"

echo "Done: dist/SoilSight-${VERSION}-mac.dmg"
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x build/build_mac.sh
```

- [ ] **Step 3: Run the Mac build script**

```bash
./build/build_mac.sh
```

Expected output (last lines):
```
Done: dist/SoilSight-1.0.0-mac.dmg
```

- [ ] **Step 4: Verify the .dmg**

```bash
open dist/SoilSight-1.0.0-mac.dmg
```

Expected: A Finder window opens showing the SoilSight.app and an Applications shortcut. Drag the app to Applications and confirm it launches.

- [ ] **Step 5: Commit**

```bash
git add build/build_mac.sh
git commit -m "build: add Mac DMG build script"
```

---

### Task 4: Create Windows build script and NSIS installer script

**Files:**
- Create: `build/build_win.ps1`
- Create: `build/installer.nsi`

> Note: These files are written on Mac but executed on Windows. Test them in CI (Task 6). The NSIS script can be validated with `makensis -V2 build/installer.nsi` on a Windows machine or the Windows CI runner.

- [ ] **Step 1: Write `build/installer.nsi`**

```nsis
; build/installer.nsi — NSIS installer script for SoilSight

!define APP_NAME "SoilSight"
!define APP_VERSION_FILE "..\VERSION"
!define INSTALL_DIR "$PROGRAMFILES\SoilSight"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\SoilSight"

; Read version from file
!searchparse /file "${APP_VERSION_FILE}" `` APP_VERSION ``

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\dist\SoilSight-${APP_VERSION}-windows-setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel admin

; Pages
Page directory
Page instfiles

; Uninstall pages
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "..\dist\SoilSight\*.*"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\SoilSight"
  CreateShortcut "$SMPROGRAMS\SoilSight\SoilSight.lnk" "$INSTDIR\SoilSight.exe"
  CreateShortcut "$DESKTOP\SoilSight.lnk" "$INSTDIR\SoilSight.exe"

  ; Write uninstall info
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\SoilSight\SoilSight.lnk"
  RMDir "$SMPROGRAMS\SoilSight"
  Delete "$DESKTOP\SoilSight.lnk"
  DeleteRegKey HKLM "${UNINSTALL_KEY}"
SectionEnd
```

- [ ] **Step 2: Write `build/build_win.ps1`**

```powershell
# build/build_win.ps1 — Windows build script for SoilSight

$ErrorActionPreference = "Stop"

# Read version
$VERSION = (Get-Content "VERSION").Trim()
Write-Host "Building SoilSight v$VERSION for Windows..."

# Activate venv
.\.venv311\Scripts\Activate.ps1

# Install build tools
pip install pyinstaller pyinstaller-hooks-contrib --quiet

# Clean previous build
if (Test-Path "dist\SoilSight") { Remove-Item -Recurse -Force "dist\SoilSight" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Run PyInstaller
pyinstaller SoilSight.spec --clean

# Build NSIS installer
makensis build\installer.nsi

Write-Host "Done: dist\SoilSight-$VERSION-windows-setup.exe"
```

- [ ] **Step 3: Commit both files**

```bash
git add build/installer.nsi build/build_win.ps1
git commit -m "build: add Windows NSIS installer script and build script"
```

---

### Task 5: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/build-release.yml`

- [ ] **Step 1: Create the workflows directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write `.github/workflows/build-release.yml`**

```yaml
name: Build & Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: macos-latest
            label: mac
          - os: windows-latest
            label: windows

    runs-on: ${{ matrix.os }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Read version
        id: version
        shell: bash
        run: echo "VERSION=$(cat VERSION)" >> $GITHUB_OUTPUT

      - name: Install dependencies
        shell: bash
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller pyinstaller-hooks-contrib

      # ── Mac ──────────────────────────────────────────────────────────────
      - name: Install create-dmg (Mac)
        if: matrix.os == 'macos-latest'
        run: brew install create-dmg

      - name: Build Mac DMG
        if: matrix.os == 'macos-latest'
        run: |
          pyinstaller SoilSight.spec --clean
          create-dmg \
            --volname "SoilSight ${{ steps.version.outputs.VERSION }}" \
            --window-pos 200 120 \
            --window-size 660 400 \
            --icon-size 100 \
            --icon "SoilSight.app" 165 185 \
            --hide-extension "SoilSight.app" \
            --app-drop-link 495 185 \
            "dist/SoilSight-${{ steps.version.outputs.VERSION }}-mac.dmg" \
            "dist/SoilSight.app"

      # ── Windows ──────────────────────────────────────────────────────────
      - name: Install NSIS (Windows)
        if: matrix.os == 'windows-latest'
        run: choco install nsis --yes

      - name: Build Windows installer
        if: matrix.os == 'windows-latest'
        shell: pwsh
        run: |
          pyinstaller SoilSight.spec --clean
          & 'C:\Program Files (x86)\NSIS\makensis.exe' build\installer.nsi

      # ── Upload ───────────────────────────────────────────────────────────
      - name: Upload Mac DMG
        if: matrix.os == 'macos-latest'
        uses: softprops/action-gh-release@v2
        with:
          files: dist/SoilSight-${{ steps.version.outputs.VERSION }}-mac.dmg

      - name: Upload Windows installer
        if: matrix.os == 'windows-latest'
        uses: softprops/action-gh-release@v2
        with:
          files: dist/SoilSight-${{ steps.version.outputs.VERSION }}-windows-setup.exe
```

- [ ] **Step 3: Commit the workflow**

```bash
git add .github/workflows/build-release.yml
git commit -m "ci: add GitHub Actions matrix build for Mac DMG and Windows installer"
```

---

### Task 6: Tag and trigger CI release

**Files:** (none changed)

- [ ] **Step 1: Push all commits to remote**

```bash
git push origin main
```

- [ ] **Step 2: Create and push a release tag**

```bash
git tag v1.0.0
git push origin v1.0.0
```

- [ ] **Step 3: Watch the CI run**

Go to: `https://github.com/<your-org>/<repo>/actions`

Expected: Two jobs (`mac`, `windows`) appear. Both should go green in ~20–40 minutes (torch install is slow).

- [ ] **Step 4: Verify release assets**

Go to: `https://github.com/<your-org>/<repo>/releases/tag/v1.0.0`

Expected: Two assets attached:
- `SoilSight-1.0.0-mac.dmg`
- `SoilSight-1.0.0-windows-setup.exe`

- [ ] **Step 5: If CI fails, check common issues**

**`ModuleNotFoundError` for a package:**
Add it to `hiddenimports` in `SoilSight.spec`, commit, retag:
```bash
git tag -d v1.0.0 && git push origin :v1.0.0
git tag v1.0.0 && git push origin v1.0.0
```

**Missing data files at runtime:**
Add the package to the `collect_all` loop in `SoilSight.spec`.

**NSIS `!searchparse` fails to read VERSION:**
Verify `VERSION` file has no trailing newline: `cat -A VERSION` should show `1.0.0$` not `1.0.0^M$`.
