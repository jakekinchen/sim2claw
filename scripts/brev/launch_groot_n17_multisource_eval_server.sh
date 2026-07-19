#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-multisource}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/home/shadeform/runs/groot-n17-multisource-v2/train/sim2claw-groot-n17-multisource-v2/checkpoint-1000}"
PROCESSOR_MODEL_PATH="/home/shadeform/model-snapshots/processor/9ce19a195e423419c349abfc86fd07178b230561"
EXPERIMENT="${SIM2CLAW_ROOT}/configs/experiments/groot_n17_multisource_v2.json"
EVIDENCE_ROOT="/home/shadeform/runs/groot-n17-multisource-v2"
CHECKPOINT_MANIFEST="${CHECKPOINT_MANIFEST:-${EVIDENCE_ROOT}/evidence/checkpoints/checkpoint-1000-manifest.json}"
CHECKPOINT_PREFLIGHT="${EVIDENCE_ROOT}/pawn-development-checkpoint-preflight.json"
EVALUATION_MANIFEST="${EVIDENCE_ROOT}/pawn-development-evaluation-implementation.json"
SERVER_LOG="${EVIDENCE_ROOT}/pawn-development-policy-server.log"
SERVER_PID_FILE="${EVIDENCE_ROOT}/pawn-development-policy-server.pid"
SERVER_RUNTIME_IDENTITY="${EVIDENCE_ROOT}/pawn-development-policy-server-runtime.json"
SERVER_SCRIPT="${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_chess_seeded_server.py"
PYTHON_BIN="${GROOT_DIR}/.venv/bin/python"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
MAX_SERVER_SECONDS="${MAX_SERVER_SECONDS:-3600}"
SERVER_READY_TIMEOUT_SECONDS="${SERVER_READY_TIMEOUT_SECONDS:-300}"

if [[ ! -d "$CHECKPOINT_DIR" || ! -f "$CHECKPOINT_MANIFEST" ]]; then
  echo "checkpoint-1000 directory or manifest is missing" >&2
  exit 1
fi
if [[ ! -x "$PYTHON_BIN" || ! -f "$SERVER_SCRIPT" || ! -f "$EXPERIMENT" ]]; then
  echo "GR00T Python runtime or seeded server script is missing" >&2
  exit 1
fi
for output in \
  "$CHECKPOINT_PREFLIGHT" \
  "$EVALUATION_MANIFEST" \
  "$SERVER_LOG" \
  "$SERVER_PID_FILE" \
  "$SERVER_RUNTIME_IDENTITY"; do
  if [[ -e "$output" ]]; then
    echo "refusing to reuse evaluation-server evidence: $output" >&2
    exit 1
  fi
done

PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_evaluation_identity freeze \
  --repo-root "$SIM2CLAW_ROOT" \
  --groot-root "$GROOT_DIR" \
  --runtime-asset "processor_model=$PROCESSOR_MODEL_PATH" \
  --output "$EVALUATION_MANIFEST"
PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_evaluation_identity verify \
  --manifest "$EVALUATION_MANIFEST" \
  --repo-root "$SIM2CLAW_ROOT" \
  --groot-root "$GROOT_DIR" \
  --runtime-asset "processor_model=$PROCESSOR_MODEL_PATH" >/dev/null
observed_processor_inventory_sha256="$(
  "$PYTHON_BIN" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["runtime_assets"]["processor_model"]["inventory_sha256"])' \
    "$EVALUATION_MANIFEST"
)"
expected_processor_inventory_sha256="$(
  "$PYTHON_BIN" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["frozen_identities"]["processor_inventory_sha256"])' \
    "$EXPERIMENT"
)"
if [[ "$observed_processor_inventory_sha256" != "$expected_processor_inventory_sha256" ]]; then
  echo "processor model inventory differs from the frozen experiment" >&2
  exit 1
fi

PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_server_identity checkpoint-preflight \
  --manifest "$CHECKPOINT_MANIFEST" \
  --checkpoint "$CHECKPOINT_DIR" \
  --output "$CHECKPOINT_PREFLIGHT"
checkpoint_manifest_sha256="$(
  "$PYTHON_BIN" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["checkpoint_manifest_sha256"])' \
    "$CHECKPOINT_PREFLIGHT"
)"
checkpoint_payload_sha256="$(
  "$PYTHON_BIN" -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["checkpoint_payload_sha256"])' \
    "$CHECKPOINT_PREFLIGHT"
)"
evaluation_manifest_sha256="$(
  "$PYTHON_BIN" -c \
    'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$EVALUATION_MANIFEST"
)"

server_pid=""
cleanup_failed_launch() {
  status="$?"
  if [[ "$status" -ne 0 && -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  trap - EXIT
  exit "$status"
}
trap cleanup_failed_launch EXIT

cd "$GROOT_DIR"
nohup env \
  HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 \
  NO_ALBUMENTATIONS_UPDATE=1 \
  GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
  GROOT_BACKBONE_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
  PYTHONPATH="${SIM2CLAW_ROOT}/src" \
  "$PYTHON_BIN" -u "$SERVER_SCRIPT" \
    --model-path "$CHECKPOINT_DIR" \
    --processor-model-path "$PROCESSOR_MODEL_PATH" \
    --embodiment-tag new_embodiment \
    --device cuda \
    --host "$SERVER_HOST" \
    --port "$SERVER_PORT" \
    --proposal-count 5 \
    --action-aggregation median \
    --noise-scale 0.5 \
    --num-inference-timesteps 4 \
    --checkpoint-manifest-sha256 "$checkpoint_manifest_sha256" \
    --checkpoint-payload-sha256 "$checkpoint_payload_sha256" \
    --evaluation-manifest-sha256 "$evaluation_manifest_sha256" \
    --maximum-runtime-seconds "$MAX_SERVER_SECONDS" \
  >"$SERVER_LOG" 2>&1 < /dev/null &

server_pid="$!"
printf '%s\n' "$server_pid" > "$SERVER_PID_FILE"
PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_server_identity wait \
  --pid "$server_pid" \
  --host "$SERVER_HOST" \
  --port "$SERVER_PORT" \
  --timeout-seconds "$SERVER_READY_TIMEOUT_SECONDS"
PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_server_identity emit \
  --manifest "$CHECKPOINT_MANIFEST" \
  --checkpoint "$CHECKPOINT_DIR" \
  --evaluation-manifest "$EVALUATION_MANIFEST" \
  --server-script "$SERVER_SCRIPT" \
  --pid "$server_pid" \
  --host "$SERVER_HOST" \
  --port "$SERVER_PORT" \
  --output "$SERVER_RUNTIME_IDENTITY"
PYTHONPATH="${SIM2CLAW_ROOT}/src" "$PYTHON_BIN" -m \
  sim2claw.groot_server_identity verify \
  --identity "$SERVER_RUNTIME_IDENTITY" \
  --manifest "$CHECKPOINT_MANIFEST" \
  --evaluation-manifest "$EVALUATION_MANIFEST" \
  --host "$SERVER_HOST" \
  --port "$SERVER_PORT" >/dev/null

trap - EXIT
printf 'multisource pawn development server started pid=%s port=%s identity=%s\n' \
  "$server_pid" "$SERVER_PORT" "$SERVER_RUNTIME_IDENTITY"
