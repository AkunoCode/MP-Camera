# build/build_win.ps1 — Windows build script for SoilSight

$ErrorActionPreference = "Stop"

# Read version
$VERSION = (Get-Content "VERSION").Trim()
Write-Host "Building SoilSight v$VERSION for Windows..."

# Activate venv
.\.venv311\Scripts\Activate.ps1

# Install build tools
pip install pyinstaller pyinstaller-hooks-contrib --quiet

# Clean previous build (but not the build directory itself)
if (Test-Path "dist\SoilSight") { Remove-Item -Recurse -Force "dist\SoilSight" }
if (Test-Path "build\SoilSight") { Remove-Item -Recurse -Force "build\SoilSight" }

# Run PyInstaller
pyinstaller SoilSight.spec --clean

# Build NSIS installer
makensis build\installer.nsis

Write-Host "Done: dist\SoilSight-$VERSION-windows-setup.exe"
