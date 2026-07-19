#!/usr/bin/env bash
set -euo pipefail

export SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
export DATASET_ROOT="${DATASET_ROOT:-$SIM2CLAW_ROOT/datasets/chess_pick_place_groot_recovery_v2}"
export RUN_DIR="${RUN_DIR:-/home/shadeform/runs/groot-n17-recovery-candidate-a}"
export OUTPUT_ROOT="${OUTPUT_ROOT:-$RUN_DIR/checkpoints}"
export EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-recovery-5k}"
export RUN_LABEL="${RUN_LABEL:-candidate-a}"
export MAX_RUNTIME_SECONDS="${MAX_RUNTIME_SECONDS:-21600}"
export MAX_STEPS="${MAX_STEPS:-5000}"
export SAVE_STEPS="${SAVE_STEPS:-1000}"
export GLOBAL_BATCH_SIZE="${GLOBAL_BATCH_SIZE:-16}"
export TRAIN_SCRIPT="${TRAIN_SCRIPT:-$SIM2CLAW_ROOT/scripts/brev/run_groot_n17_chess_finetune.sh}"

exec bash "$SIM2CLAW_ROOT/scripts/brev/launch_groot_n17_chess_finetune.sh"
