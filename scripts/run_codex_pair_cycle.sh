#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec docs/autonomous-workflow/reusable/scripts/run-codex-pair-cycle.sh "$@"
