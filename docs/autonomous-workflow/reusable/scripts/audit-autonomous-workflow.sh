#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
ROOT="$(cd "$ROOT" && pwd)"
cd "$ROOT"

exec uv run --locked sim2claw check --profile agent --root "$ROOT"
