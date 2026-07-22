#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-bg-v2}"
DATASET_ROOT="${DATASET_ROOT:-/home/shadeform/groot_n17_physical_bg_exploratory_20260719}"
RUN_ROOT="${RUN_ROOT:-/home/shadeform/runs/groot-n17-physical-bg-exploratory-v1}"
PROCESSOR_ROOT="${PROCESSOR_ROOT:-/home/shadeform/models/cosmos-reason2-2b}"
BASELINE_CHECKPOINT="${BASELINE_CHECKPOINT:-$RUN_ROOT/eval-snapshots/checkpoint-2000}"
CANDIDATE_CHECKPOINT="${CANDIDATE_CHECKPOINT:-$RUN_ROOT/train/sim2claw-groot-n17-physical-bg-exploratory-v1/checkpoint-3000}"
EVALUATION_ROOT="${EVALUATION_ROOT:-$RUN_ROOT/evaluation/full-window-317-v1}"
DIAGNOSTIC_SEED="${DIAGNOSTIC_SEED:-20260719}"
STEPS="${STEPS:-317}"
TRAJECTORIES=(0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17)

mkdir -p "$EVALUATION_ROOT"
for required in "$BASELINE_CHECKPOINT" "$CANDIDATE_CHECKPOINT" "$DATASET_ROOT"; do
  if [[ ! -d "$required" ]]; then
    echo "required input directory is missing: $required" >&2
    exit 1
  fi
done

run_evaluation() {
  local checkpoint="$1"
  local label="$2"
  local log="$EVALUATION_ROOT/$label.log"
  local plot="$EVALUATION_ROOT/$label.png"
  if [[ -e "$log" || -e "$plot" ]]; then
    echo "refusing to overwrite evaluation output for $label" >&2
    exit 1
  fi
  cd "$GROOT_ROOT"
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
      --model-path "$checkpoint" \
      --traj-ids "${TRAJECTORIES[@]}" \
      --steps "$STEPS" \
      --action-horizon 16 \
      --save-plot-path "$plot" \
      >"$log" 2>&1
}

run_evaluation "$BASELINE_CHECKPOINT" checkpoint-2000
run_evaluation "$CANDIDATE_CHECKPOINT" checkpoint-3000
printf '0\n' >"$EVALUATION_ROOT/evaluation.exit"
