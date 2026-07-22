#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-bg-v2}"
DATASET_ROOT="${DATASET_ROOT:-/home/shadeform/groot_n17_physical_bg_counterfactual_language_20260719}"
RUN_ROOT="${RUN_ROOT:-/home/shadeform/runs/groot-n17-physical-bg-exploratory-v1}"
PROCESSOR_ROOT="${PROCESSOR_ROOT:-/home/shadeform/models/cosmos-reason2-2b}"
CHECKPOINT="${CHECKPOINT:-$RUN_ROOT/train/sim2claw-groot-n17-physical-bg-exploratory-v1/checkpoint-5000}"
EVALUATION_ROOT="${EVALUATION_ROOT:-$RUN_ROOT/evaluation/counterfactual-language-317-v1}"
DIAGNOSTIC_SEED="${DIAGNOSTIC_SEED:-20260719}"
STEPS="${STEPS:-317}"
TRAJECTORIES=(0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17)

for required in \
  "$CHECKPOINT" \
  "$DATASET_ROOT" \
  "$DATASET_ROOT/counterfactual_language_receipt.json"; do
  if [[ ! -e "$required" ]]; then
    echo "required counterfactual evaluation input is missing: $required" >&2
    exit 1
  fi
done

mkdir -p "$EVALUATION_ROOT"
LOG="$EVALUATION_ROOT/checkpoint-5000-wrong-instructions.log"
PLOT="$EVALUATION_ROOT/checkpoint-5000-wrong-instructions.png"
if [[ -e "$LOG" || -e "$PLOT" ]]; then
  echo "refusing to overwrite counterfactual evaluation output" >&2
  exit 1
fi

cd "$GROOT_ROOT"
set +e
CUDA_VISIBLE_DEVICES=0 \
GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_ROOT" \
GROOT_BACKBONE_MODEL_PATH="$PROCESSOR_ROOT" \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
NO_ALBUMENTATIONS_UPDATE=1 \
  /home/shadeform/.local/bin/uv run python \
    "$SIM2CLAW_ROOT/scripts/brev/run_groot_n17_open_loop_eval.py" \
    --diagnostic-seed "$DIAGNOSTIC_SEED" \
    --dataset-path "$DATASET_ROOT" \
    --embodiment-tag new_embodiment \
    --model-path "$CHECKPOINT" \
    --traj-ids "${TRAJECTORIES[@]}" \
    --steps "$STEPS" \
    --action-horizon 16 \
    --save-plot-path "$PLOT" \
    >"$LOG" 2>&1
status=$?
set -e
printf '%s\n' "$status" >"$EVALUATION_ROOT/evaluation.exit"
exit "$status"
