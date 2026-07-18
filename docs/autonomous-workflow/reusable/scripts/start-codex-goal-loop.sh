#!/usr/bin/env bash
set -euo pipefail

ROOT="$PWD"
INTERVAL="60"
MAX_CYCLES="10"
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  start-codex-goal-loop.sh [options] [-- runner options]

Options:
  --root <dir>          Target repo. Default: current directory.
  --interval <seconds>  Delay between loop cycles. Default: 60.
  --max-cycles <n>      Maximum cycles. Default: 10.
  -h, --help            Show help.

Additional arguments after -- are passed to run-codex-pair-cycle.sh.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      ROOT="${2:?--root requires a directory}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:?--interval requires seconds}"
      shift 2
      ;;
    --max-cycles)
      MAX_CYCLES="${2:?--max-cycles requires a number}"
      shift 2
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$ROOT" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_slug="$(basename "$ROOT" | tr -cs 'a-zA-Z0-9._-' '-')"
runtime_dir="/tmp/autonomous-project-workflow/$repo_slug"
mkdir -p "$runtime_dir"

pid_file="$ROOT/.codex-goal-loop.pid"
if [ -f "$pid_file" ]; then
  old_pid="$(cat "$pid_file")"
  if kill -0 "$old_pid" 2>/dev/null; then
    printf 'Loop already running with pid %s\n' "$old_pid" >&2
    exit 1
  fi
  rm -f "$pid_file"
fi

log_file="$runtime_dir/goal-loop.log"

if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
  nohup "$SCRIPT_DIR/run-codex-pair-cycle.sh" \
    --loop \
    --root "$ROOT" \
    --interval "$INTERVAL" \
    --max-cycles "$MAX_CYCLES" \
    "${EXTRA_ARGS[@]}" \
    >> "$log_file" 2>&1 &
else
  nohup "$SCRIPT_DIR/run-codex-pair-cycle.sh" \
    --loop \
    --root "$ROOT" \
    --interval "$INTERVAL" \
    --max-cycles "$MAX_CYCLES" \
    >> "$log_file" 2>&1 &
fi

pid="$!"
printf '%s\n' "$pid" > "$pid_file"

printf 'Started Codex goal loop for %s\n' "$ROOT"
printf 'pid: %s\n' "$pid"
printf 'log: %s\n' "$log_file"
printf 'stop: scripts/stop_codex_goal_loop.sh\n'
