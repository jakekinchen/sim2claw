#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
APP="$ROOT/Sim2ClawDemoControl.app"
if [[ ! -d "$APP" ]]; then
  echo "ERROR: Package the app first with Scripts/package_app.sh" >&2
  exit 1
fi
open -n "$APP"
