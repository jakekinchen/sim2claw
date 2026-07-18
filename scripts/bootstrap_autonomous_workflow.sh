#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/../docs/autonomous-workflow/reusable/scripts/bootstrap-autonomous-workflow.sh" "${1:-$PWD}"
