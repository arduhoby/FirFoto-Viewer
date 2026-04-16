#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$ROOT_DIR/firfoto_viewer"
APP_NAME="firfoto_viewer"
APP_BUNDLE="$PROJECT_DIR/build/macos/Build/Products/Debug/${APP_NAME}.app"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/${APP_NAME}"

kill_existing() {
  pkill -x "$APP_NAME" >/dev/null 2>&1 || true
}

build_app() {
  (cd "$PROJECT_DIR" && flutter build macos --debug)
}

launch_app() {
  /usr/bin/open -n "$APP_BUNDLE"
}

stream_logs() {
  /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
}

stream_telemetry() {
  /usr/bin/log stream --info --style compact --predicate "process == \"$APP_NAME\""
}

case "$MODE" in
  run)
    kill_existing
    build_app
    launch_app
    ;;
  --debug|debug)
    kill_existing
    build_app
    if command -v lldb >/dev/null 2>&1; then
      lldb -- "$APP_BINARY"
    else
      echo "lldb is not available on this system." >&2
      exit 1
    fi
    ;;
  --logs|logs)
    kill_existing
    build_app
    launch_app
    stream_logs
    ;;
  --telemetry|telemetry)
    kill_existing
    build_app
    launch_app
    stream_telemetry
    ;;
  --verify|verify)
    kill_existing
    build_app
    launch_app
    sleep 2
    pgrep -x "$APP_NAME" >/dev/null
    ;;
  *)
    echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2
    exit 2
    ;;
esac
