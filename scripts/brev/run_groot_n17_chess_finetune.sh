#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
DATASET_ROOT="${DATASET_ROOT:-$SIM2CLAW_ROOT/datasets/chess_pick_place_groot_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-chess}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-chess}"
MODEL_REVISION="2fc962b973bccdd5d8ce4f67cc63b264d6886495"
MODEL_CACHE="${MODEL_CACHE:-/home/shadeform/.cache/huggingface/hub/models--nvidia--GR00T-N1.7-3B/snapshots/$MODEL_REVISION}"
BASE_MODEL_PATH="${BASE_MODEL_PATH:-$MODEL_CACHE}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.8}"

if [ ! -x "$CUDA_HOME/bin/nvcc" ]; then
  echo "CUDA compiler missing: $CUDA_HOME/bin/nvcc" >&2
  exit 1
fi
export CUDA_HOME
export PATH="$CUDA_HOME/bin:$PATH"

MAX_STEPS="${MAX_STEPS:-250}"
SAVE_STEPS="${SAVE_STEPS:-125}"
GLOBAL_BATCH_SIZE="${GLOBAL_BATCH_SIZE:-16}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
STATE_DROPOUT_PROB="${STATE_DROPOUT_PROB:-0.1}"

if [ ! -d "$BASE_MODEL_PATH" ]; then
  echo "base model or checkpoint missing: $BASE_MODEL_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_ROOT"
cd "$GROOT_ROOT"

env \
  CUDA_VISIBLE_DEVICES=0 \
  NUM_GPUS=1 \
  MAX_STEPS="$MAX_STEPS" \
  SAVE_STEPS="$SAVE_STEPS" \
  USE_WANDB=0 \
  GLOBAL_BATCH_SIZE="$GLOBAL_BATCH_SIZE" \
  DATALOADER_NUM_WORKERS=4 \
  SHARD_SIZE=128 \
  NUM_SHARDS_PER_EPOCH=64 \
  EPISODE_SAMPLING_RATE=0.1 \
  "$UV_BIN" run bash examples/finetune.sh \
    --base-model-path "$BASE_MODEL_PATH" \
    --dataset-path "$DATASET_ROOT" \
    --modality-config-path "$SIM2CLAW_ROOT/configs/groot/sim2claw_so101_config.py" \
    --embodiment-tag NEW_EMBODIMENT \
    --output-dir "$OUTPUT_ROOT" \
    --experiment-name "$EXPERIMENT_NAME" \
    --state-dropout-prob "$STATE_DROPOUT_PROB" \
    --save-only-model \
    -- \
    --learning_rate "$LEARNING_RATE"
