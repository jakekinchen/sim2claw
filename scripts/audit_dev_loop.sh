#!/usr/bin/env bash
set -euo pipefail
root="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$root"
exec uv run sim2claw dev-loop-audit --root "$root"
