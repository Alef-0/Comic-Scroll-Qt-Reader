#!/usr/bin/env bash
# ==============================================================================
# Comic Scroll Reader - macOS Disk Image (.dmg) Builder
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build"
DIST_DIR="$PROJECT_ROOT/dist"

echo "======================================================================"
echo " Building macOS DMG for Comic Scroll Reader"
echo "======================================================================"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Error: macOS DMG packages must be built on macOS." >&2
    exit 1
fi

PYTHON_BIN="python3"
if [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi

echo "[1/3] Ensuring dependencies..."
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt" pyinstaller pillow

echo "[2/3] Compiling .app bundle with PyInstaller..."
"$PYTHON_BIN" -m PyInstaller \
    --distpath "$BUILD_DIR/pyinstaller_dist" \
    --workpath "$BUILD_DIR/pyinstaller_build" \
    -y \
    "$SCRIPT_DIR/comic-scroll-reader-mac.spec"

APP_BUNDLE="$BUILD_DIR/pyinstaller_dist/Comic Scroll Reader.app"
if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: .app bundle not generated at $APP_BUNDLE" >&2
    exit 1
fi

echo "[3/3] Creating DMG disk image..."
mkdir -p "$DIST_DIR"
DMG_STAGE="$BUILD_DIR/dmg_stage"
rm -rf "$DMG_STAGE"
mkdir -p "$DMG_STAGE"

cp -R "$APP_BUNDLE" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"

DMG_OUTPUT="$DIST_DIR/Comic-Scroll-Reader-1.0.0.dmg"
rm -f "$DMG_OUTPUT"

hdiutil create \
    -volname "Comic Scroll Reader" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDZO \
    "$DMG_OUTPUT"

echo "======================================================================"
echo " macOS build complete! Disk image: $DMG_OUTPUT"
echo "======================================================================"
