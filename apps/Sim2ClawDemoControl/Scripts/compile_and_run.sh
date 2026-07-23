#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP_NAME=Sim2ClawDemoControl
APP="$ROOT/${APP_NAME}.app"

pkill -x "$APP_NAME" 2>/dev/null || true
swift test --package-path "$ROOT" -q
"$ROOT/Scripts/package_app.sh" release
open -n "$APP"

for _ in {1..10}; do
  if pgrep -x "$APP_NAME" >/dev/null; then
    echo "OK: $APP_NAME is running."
    exit 0
  fi
  sleep 0.4
done
echo "ERROR: $APP_NAME exited during launch." >&2
exit 1
