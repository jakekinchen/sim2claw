#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
ROOT="$(cd "$ROOT" && pwd)"
pid_file="$ROOT/.codex-goal-loop.pid"

if [ ! -f "$pid_file" ]; then
  printf 'No loop pid file found at %s\n' "$pid_file"
  exit 0
fi

pid="$(cat "$pid_file")"
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  printf 'Stopped Codex goal loop pid %s\n' "$pid"
else
  printf 'Loop pid %s is not running\n' "$pid"
fi

rm -f "$pid_file"
