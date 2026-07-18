#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/home/shadeform/runs/groot-n17-placement/checkpoint-4000}"
SERVER_LOG="${SERVER_LOG:-/home/shadeform/runs/groot-n17-placement/policy-server-seeded.log}"
SERVER_PID_FILE="${SERVER_PID_FILE:-/home/shadeform/runs/groot-n17-placement/policy-server-seeded.pid}"
SERVER_PORT="${SERVER_PORT:-5555}"
MAX_SERVER_SECONDS="${MAX_SERVER_SECONDS:-14400}"
HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"
PROPOSAL_COUNT="${PROPOSAL_COUNT:-1}"
ACTION_AGGREGATION="${ACTION_AGGREGATION:-medoid}"
NOISE_SCALE="${NOISE_SCALE:-1.0}"

if [[ ! -d "${CHECKPOINT_DIR}" ]]; then
  echo "checkpoint directory not found: ${CHECKPOINT_DIR}" >&2
  exit 1
fi

if [[ -f "${SERVER_PID_FILE}" ]]; then
  existing_pid="$(cat "${SERVER_PID_FILE}")"
  if kill -0 "${existing_pid}" 2>/dev/null; then
    echo "seeded policy server already running as PID ${existing_pid}" >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "${SERVER_LOG}")"
cd "${GROOT_DIR}"
nohup timeout "${MAX_SERVER_SECONDS}" \
  env \
    HF_HUB_OFFLINE="${HF_HUB_OFFLINE}" \
    PYTHONPATH="${SIM2CLAW_ROOT}/src" \
    /home/shadeform/.local/bin/uv run python -u \
      "${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_chess_seeded_server.py" \
      --model-path "${CHECKPOINT_DIR}" \
      --embodiment-tag new_embodiment \
      --device cuda \
      --host 127.0.0.1 \
      --port "${SERVER_PORT}" \
      --proposal-count "${PROPOSAL_COUNT}" \
      --action-aggregation "${ACTION_AGGREGATION}" \
      --noise-scale "${NOISE_SCALE}" \
  >"${SERVER_LOG}" 2>&1 </dev/null &
server_pid=$!
echo "${server_pid}" >"${SERVER_PID_FILE}"
echo "launched seeded GR00T policy server wrapper PID ${server_pid}"
