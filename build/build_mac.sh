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

# Clean previous build (but not the build directory itself)
rm -rf dist/SoilSight.app dist/SoilSight build/SoilSight

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
  "dist/SoilSight.app" 2>&1 || true

# Rename temporary DMG if needed
if [ -f "dist/rw."*".SoilSight-${VERSION}-mac.dmg" ]; then
  mv dist/rw.*"SoilSight-${VERSION}-mac.dmg" "dist/SoilSight-${VERSION}-mac.dmg"
fi

echo "Done: dist/SoilSight-${VERSION}-mac.dmg"
