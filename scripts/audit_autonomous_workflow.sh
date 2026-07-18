#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/../docs/autonomous-workflow/reusable/scripts/audit-autonomous-workflow.sh" "${1:-$PWD}"
