#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/firfoto_viewer"
BUILD_DIR="$PROJECT_DIR/build/macos/Build/Products/Release"
SOURCE_APP="$BUILD_DIR/firfoto_viewer.app"
DIST_DIR="$ROOT_DIR/dist"
STAGING_DIR="$DIST_DIR/dmg-root"
DISPLAY_NAME="FirFoto Viewer"
STAGED_APP="$STAGING_DIR/$DISPLAY_NAME.app"
DMG_PATH="$DIST_DIR/FirFoto-Viewer.dmg"
VOL_NAME="$DISPLAY_NAME"
TEMP_DMG="$DIST_DIR/FirFoto-Viewer-temp.dmg"

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "Release app not found: $SOURCE_APP" >&2
  echo "Build a release app first." >&2
  exit 1
fi

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
mkdir -p "$DIST_DIR"

/usr/bin/ditto "$SOURCE_APP" "$STAGED_APP"
ln -sfn /Applications "$STAGING_DIR/Applications"
rm -f "$DMG_PATH"
rm -f "$TEMP_DMG"

SIZE_KB=$(du -sk "$STAGING_DIR" | awk '{print $1 + 8192}')

hdiutil create \
  -volname "$VOL_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDRW \
  -size "${SIZE_KB}k" \
  "$TEMP_DMG"

MOUNT_POINT="$(hdiutil attach -readwrite -noverify -noautoopen "$TEMP_DMG" | awk -F '\t' '/\/Volumes\// {print $3}' | tail -n 1)"

osascript <<OSA
tell application "Finder"
  tell disk "$VOL_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {140, 140, 760, 500}
    set theViewOptions to the icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 144
    set text size of theViewOptions to 14
    set position of item "$DISPLAY_NAME.app" of container window to {170, 210}
    set position of item "Applications" of container window to {470, 210}
    close
    open
    update without registering applications
    delay 2
  end tell
end tell
OSA

sync
hdiutil detach "$MOUNT_POINT"

hdiutil convert "$TEMP_DMG" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  -o "$DMG_PATH"

rm -f "$TEMP_DMG"

echo "Created DMG:"
echo "$DMG_PATH"
