#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-multisource}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/home/shadeform/runs/groot-n17-multisource-v2/train/sim2claw-groot-n17-multisource-v2/checkpoint-1000}"
PROCESSOR_MODEL_PATH="/home/shadeform/model-snapshots/processor/9ce19a195e423419c349abfc86fd07178b230561"
EVIDENCE_ROOT="/home/shadeform/runs/groot-n17-multisource-v2"
SERVER_LOG="${EVIDENCE_ROOT}/pawn-development-policy-server.log"
SERVER_PID_FILE="${EVIDENCE_ROOT}/pawn-development-policy-server.pid"
SERVER_PORT=5555
MAX_SERVER_SECONDS=3600

if [[ ! -d "$CHECKPOINT_DIR" ]]; then
  echo "checkpoint-1000 is missing" >&2
  exit 1
fi
if [[ -e "$SERVER_LOG" ]]; then
  echo "refusing to reuse evaluation server log" >&2
  exit 1
fi
if [[ -f "$SERVER_PID_FILE" ]]; then
  existing_pid="$(<"$SERVER_PID_FILE")"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "evaluation server is already running: $existing_pid" >&2
    exit 1
  fi
  echo "stale evaluation server PID receipt exists" >&2
  exit 1
fi

cd "$GROOT_DIR"
nohup timeout "$MAX_SERVER_SECONDS" env \
  HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 \
  NO_ALBUMENTATIONS_UPDATE=1 \
  GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
  GROOT_BACKBONE_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
  PYTHONPATH="${SIM2CLAW_ROOT}/src" \
  /home/shadeform/.local/bin/uv run python -u \
    "${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_chess_seeded_server.py" \
    --model-path "$CHECKPOINT_DIR" \
    --embodiment-tag new_embodiment \
    --device cuda \
    --host 127.0.0.1 \
    --port "$SERVER_PORT" \
    --proposal-count 5 \
    --action-aggregation median \
    --noise-scale 0.5 \
    --num-inference-timesteps 4 \
  >"$SERVER_LOG" 2>&1 < /dev/null &

server_pid="$!"
printf '%s\n' "$server_pid" > "$SERVER_PID_FILE"
printf 'multisource pawn development server started pid=%s port=%s\n' \
  "$server_pid" "$SERVER_PORT"
