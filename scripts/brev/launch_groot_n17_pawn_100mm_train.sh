#!/usr/bin/env bash
set -euo pipefail

EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:?expected experiment hash is required}"
TRAINING_WRAPPER="${TRAINING_WRAPPER:-/home/shadeform/sim2claw-pawn/scripts/brev/run_groot_n17_pawn_100mm_train.sh}"
EVIDENCE_ROOT="/home/shadeform/runs/groot-n17-pawn-100mm-v1"
OUTPUT_ROOT="${EVIDENCE_ROOT}/train"
PID_FILE="${EVIDENCE_ROOT}/training-supervisor.pid"
EXIT_FILE="${EVIDENCE_ROOT}/training.exit"
LOG_FILE="${EVIDENCE_ROOT}/training.log"
MAX_RUNTIME_SECONDS=10800

install -d -m 755 "$EVIDENCE_ROOT"
if [[ -e "$OUTPUT_ROOT" || -e "$EXIT_FILE" || -e "$LOG_FILE" ]]; then
  echo "refusing to reuse pawn training launch state" >&2
  exit 1
fi
if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "pawn training supervisor is already running: $existing_pid" >&2
    exit 1
  fi
  echo "stale pawn training supervisor receipt exists" >&2
  exit 1
fi

nohup bash -c '
  set +e
  timeout --signal=TERM "$1" env \
    EXPECTED_EXPERIMENT_SHA256="$2" \
    bash "$3"
  rc=$?
  printf "%s\n" "$rc" > "$4"
  exit "$rc"
' _ "$MAX_RUNTIME_SECONDS" "$EXPECTED_EXPERIMENT_SHA256" "$TRAINING_WRAPPER" "$EXIT_FILE" \
  >"$LOG_FILE" 2>&1 < /dev/null &

supervisor_pid="$!"
printf '%s\n' "$supervisor_pid" > "$PID_FILE"
printf 'pawn training started supervisor_pid=%s max_runtime_seconds=%s experiment_sha256=%s\n' \
  "$supervisor_pid" "$MAX_RUNTIME_SECONDS" "$EXPECTED_EXPERIMENT_SHA256"
