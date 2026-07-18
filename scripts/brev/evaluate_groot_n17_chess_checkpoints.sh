#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
RUN_ROOT="${RUN_ROOT:-/home/shadeform/runs/groot-n17-chess}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-chess-5k}"
DATASET_ROOT="${DATASET_ROOT:-/home/shadeform/sim2claw/datasets/chess_pick_place_groot_v1_held_out}"
STEPS_TO_EVALUATE="${STEPS_TO_EVALUATE:-1000 2000 3000 4000 5000}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"

cd "${GROOT_DIR}"
for step in ${STEPS_TO_EVALUATE}; do
  checkpoint="${RUN_ROOT}/${EXPERIMENT_NAME}/checkpoint-${step}"
  log="${RUN_ROOT}/held-out-open-loop-${step}.log"
  if [[ ! -d "${checkpoint}" ]]; then
    echo "checkpoint missing: ${checkpoint}" >&2
    exit 1
  fi
  echo "evaluating checkpoint-${step}"
  "${UV_BIN}" run python gr00t/eval/open_loop_eval.py \
    --dataset-path "${DATASET_ROOT}" \
    --embodiment-tag new_embodiment \
    --model-path "${checkpoint}" \
    --traj-ids 0 1 2 3 \
    --steps 363 \
    --action-horizon 16 \
    >"${log}" 2>&1
  grep "Average MSE\|Average MAE" "${log}"
done
