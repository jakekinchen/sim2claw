#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/home/shadeform/runs/groot-n17-placement/checkpoint-4000}"
CHECKPOINT_ID="${CHECKPOINT_ID:-checkpoint-4000}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-placement/horizon-sweep}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
HORIZONS="${HORIZONS:-8 4 2 1}"
EPISODE_INDICES="${EPISODE_INDICES:-0}"
ROLLOUT_REPLICATE="${ROLLOUT_REPLICATE:-0}"
INFERENCE_SEED="${INFERENCE_SEED:-$ROLLOUT_REPLICATE}"
POLICY_SERVER_MODE="${POLICY_SERVER_MODE:-official_unseeded}"
MUJOCO_GL_BACKEND="${MUJOCO_GL_BACKEND:-egl}"
PYOPENGL_BACKEND="${PYOPENGL_BACKEND:-${MUJOCO_GL_BACKEND}}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
: "${CHECKPOINT_MANIFEST_SHA256:?CHECKPOINT_MANIFEST_SHA256 is required}"

if [[ ! -d "${CHECKPOINT_DIR}" ]]; then
  echo "checkpoint directory missing: ${CHECKPOINT_DIR}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_ROOT}"
cd "${GROOT_DIR}"

for horizon in ${HORIZONS}; do
  for episode_index in ${EPISODE_INDICES}; do
    output="${OUTPUT_ROOT}/episode-${episode_index}-horizon-${horizon}-replicate-${ROLLOUT_REPLICATE}"
    log="${OUTPUT_ROOT}/episode-${episode_index}-horizon-${horizon}-replicate-${ROLLOUT_REPLICATE}.log"
    if [[ -f "${output}/receipt.json" ]]; then
      echo "skipping completed episode=${episode_index} horizon=${horizon}"
      continue
    fi
    echo "running episode=${episode_index} horizon=${horizon}"
    env \
      MUJOCO_GL="${MUJOCO_GL_BACKEND}" \
      PYOPENGL_PLATFORM="${PYOPENGL_BACKEND}" \
      PYTHONPATH="${SIM2CLAW_ROOT}/src" \
      "${UV_BIN}" run python \
        "${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_chess_closed_loop.py" \
        --episode-index "${episode_index}" \
        --rollout-replicate "${ROLLOUT_REPLICATE}" \
        --inference-seed "${INFERENCE_SEED}" \
        --policy-server-mode "${POLICY_SERVER_MODE}" \
        --checkpoint-id "${CHECKPOINT_ID}" \
        --checkpoint-manifest-sha256 "${CHECKPOINT_MANIFEST_SHA256}" \
        --host "${SERVER_HOST}" \
        --port "${SERVER_PORT}" \
        --execution-horizon "${horizon}" \
        --output "${output}" \
        >"${log}" 2>&1
    jq -c \
      '{episode_index,rollout_replicate,inference_seed,policy_server_mode,execution_horizon,maximum_piece_rise_m,verdict}' \
      "${output}/receipt.json"
  done
done
