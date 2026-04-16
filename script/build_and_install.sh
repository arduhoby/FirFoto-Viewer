#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/firfoto_viewer"
BUILD_MODE="${1:-release}"
TARGET_DIR="${2:-/Applications}"
APP_NAME="firfoto_viewer.app"

if [[ "$BUILD_MODE" != "debug" && "$BUILD_MODE" != "release" ]]; then
  echo "usage: $0 [debug|release] [target-dir]" >&2
  exit 2
fi

if [[ "$BUILD_MODE" == "debug" ]]; then
  BUILD_FOLDER="Debug"
else
  BUILD_FOLDER="Release"
fi

APP_BUNDLE="$PROJECT_DIR/build/macos/Build/Products/$BUILD_FOLDER/$APP_NAME"
TARGET_APP="$TARGET_DIR/$APP_NAME"

echo "Building FirFoto Viewer ($BUILD_MODE)..."
(cd "$PROJECT_DIR" && flutter build macos "--$BUILD_MODE")

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Build output not found: $APP_BUNDLE" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"
/usr/bin/ditto "$APP_BUNDLE" "$TARGET_APP"

if [[ -x /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister ]]; then
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$TARGET_APP" >/dev/null 2>&1 || true
fi

echo "Installed to: $TARGET_APP"
echo "You can launch it from Applications or with:"
echo "open \"$TARGET_APP\""
