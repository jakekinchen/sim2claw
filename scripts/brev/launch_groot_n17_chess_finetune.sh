#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="${RUN_DIR:-/home/shadeform/runs/groot-n17-chess}"
TRAIN_SCRIPT="${TRAIN_SCRIPT:-/home/shadeform/sim2claw/scripts/brev/run_groot_n17_chess_finetune.sh}"
MAX_RUNTIME_SECONDS="${MAX_RUNTIME_SECONDS:-21600}"
MAX_STEPS="${MAX_STEPS:-250}"
SAVE_STEPS="${SAVE_STEPS:-125}"
GLOBAL_BATCH_SIZE="${GLOBAL_BATCH_SIZE:-16}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-chess}"
RUN_LABEL="${RUN_LABEL:-training}"
PID_FILE="${RUN_LABEL}.pid"
EXIT_FILE="${RUN_LABEL}.exit"
LOG_FILE="${RUN_LABEL}.log"

install -d -m 755 "$RUN_DIR"
cd "$RUN_DIR"

if [ -f "$PID_FILE" ]; then
  existing_pid="$(tr -d '\r\n' < "$PID_FILE")"
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    printf 'training already running pid=%s\n' "$existing_pid"
    exit 0
  fi
fi

rm -f "$EXIT_FILE" "$PID_FILE"
nohup bash -c '
  set +e
  timeout --signal=TERM "$1" env \
    MAX_STEPS="$3" \
    SAVE_STEPS="$4" \
    GLOBAL_BATCH_SIZE="$5" \
    EXPERIMENT_NAME="$6" \
    NUM_GPUS=1 \
    bash "$2"
  rc=$?
  printf "%s\n" "$rc" > "$7"
  exit "$rc"
' _ "$MAX_RUNTIME_SECONDS" "$TRAIN_SCRIPT" "$MAX_STEPS" "$SAVE_STEPS" \
  "$GLOBAL_BATCH_SIZE" "$EXPERIMENT_NAME" "$EXIT_FILE" \
  >"$LOG_FILE" 2>&1 < /dev/null &

training_pid="$!"
printf '%s\n' "$training_pid" > "$PID_FILE"
printf 'training started pid=%s max_runtime_seconds=%s max_steps=%s experiment=%s\n' \
  "$training_pid" "$MAX_RUNTIME_SECONDS" "$MAX_STEPS" "$EXPERIMENT_NAME"
