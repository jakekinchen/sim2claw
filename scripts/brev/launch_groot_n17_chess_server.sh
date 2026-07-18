#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/home/shadeform/runs/groot-n17-chess/sim2claw-groot-n17-chess/checkpoint-250}"
SERVER_LOG="${SERVER_LOG:-/home/shadeform/runs/groot-n17-chess/policy-server.log}"
SERVER_PID_FILE="${SERVER_PID_FILE:-/home/shadeform/runs/groot-n17-chess/policy-server.pid}"
SERVER_PORT="${SERVER_PORT:-5555}"
MAX_SERVER_SECONDS="${MAX_SERVER_SECONDS:-7200}"

if [[ ! -d "${CHECKPOINT_DIR}" ]]; then
  echo "checkpoint directory not found: ${CHECKPOINT_DIR}" >&2
  exit 1
fi

if [[ -f "${SERVER_PID_FILE}" ]]; then
  existing_pid="$(cat "${SERVER_PID_FILE}")"
  if kill -0 "${existing_pid}" 2>/dev/null; then
    echo "policy server already running as PID ${existing_pid}" >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "${SERVER_LOG}")"
cd "${GROOT_DIR}"
nohup timeout "${MAX_SERVER_SECONDS}" \
  /home/shadeform/.local/bin/uv run python -u gr00t/eval/run_gr00t_server.py \
    --model-path "${CHECKPOINT_DIR}" \
    --embodiment-tag new_embodiment \
    --device cuda \
    --host 127.0.0.1 \
    --port "${SERVER_PORT}" \
    --no-strict \
  >"${SERVER_LOG}" 2>&1 </dev/null &
server_pid=$!
echo "${server_pid}" >"${SERVER_PID_FILE}"
echo "launched GR00T policy server wrapper PID ${server_pid}"
