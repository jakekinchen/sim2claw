#!/usr/bin/env bash
set -euo pipefail

SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-pawn}"
GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
DATASET_ROOT="${DATASET_ROOT:-/home/shadeform/chess_pick_place_pawn_groot_v1}"
EXPERIMENT="${EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_pawn_100mm_v1.json}"
EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:?expected experiment hash is required}"
REMOTE_LOADER_RECEIPT="${REMOTE_LOADER_RECEIPT:-/home/shadeform/pawn-groot-remote-loader-preflight-v2.json}"
MODEL_SNAPSHOT_RECEIPT="${MODEL_SNAPSHOT_RECEIPT:-/home/shadeform/pawn-groot-model-snapshots.json}"
BASE_MODEL_PATH="/home/shadeform/.cache/huggingface/hub/models--nvidia--GR00T-N1.7-3B/snapshots/2fc962b973bccdd5d8ce4f67cc63b264d6886495"
PROCESSOR_MODEL_PATH="/home/shadeform/.cache/huggingface/hub/models--nvidia--Cosmos-Reason2-2B/snapshots/9ce19a195e423419c349abfc86fd07178b230561"
PROCESSOR_REF="/home/shadeform/.cache/huggingface/hub/models--nvidia--Cosmos-Reason2-2B/refs/main"
EVIDENCE_ROOT="/home/shadeform/runs/groot-n17-pawn-100mm-v1"
OUTPUT_ROOT="${EVIDENCE_ROOT}/train"
EXPERIMENT_NAME="sim2claw-groot-n17-pawn-100mm-v1"
UV_BIN="/home/shadeform/.local/bin/uv"
CUDA_HOME="/usr/local/cuda-12.8"
TRAINING_WRAPPER="${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_pawn_100mm_train.sh"
FINETUNE_SCRIPT="${GROOT_ROOT}/examples/finetune.sh"
PROCESSOR_FILE="${GROOT_ROOT}/gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py"

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

require_hash() {
  local path="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual="$(sha256_file "$path")"
  if [[ "$actual" != "$expected" ]]; then
    printf '%s hash mismatch: %s != %s\n' "$label" "$actual" "$expected" >&2
    exit 1
  fi
}

if [[ "$(sha256_file "$EXPERIMENT")" != "$EXPECTED_EXPERIMENT_SHA256" ]]; then
  echo "pawn experiment hash drifted" >&2
  exit 1
fi
if [[ "$(jq -r '.frozen_before_training' "$EXPERIMENT")" != "true" ]]; then
  echo "pawn experiment was not frozen before training" >&2
  exit 1
fi
if [[ "$(jq -r '.task_scope.workspace_pose_id' "$EXPERIMENT")" != "workspace_board_fiducial_robotward_100mm_20260718_v3" ]]; then
  echo "training is not bound to the current 100 mm workspace" >&2
  exit 1
fi
if [[ "$(jq -r '.task_scope.board_pose_id' "$EXPERIMENT")" != "board_robotward_100mm_20260718_v3" ]]; then
  echo "training is not bound to the current 100 mm board pose" >&2
  exit 1
fi
if [[ "$(jq -r '.task_scope.historical_72mm_authority' "$EXPERIMENT")" != "false" ]]; then
  echo "historical 72 mm evidence gained current authority" >&2
  exit 1
fi

require_hash "$TRAINING_WRAPPER" "$(jq -r '.frozen_identities.training_wrapper_sha256' "$EXPERIMENT")" "training wrapper"
require_hash "${SIM2CLAW_ROOT}/configs/tasks/chess_pick_place_pawn_groot_dataset_v1.json" "$(jq -r '.frozen_identities.dataset_contract_sha256' "$EXPERIMENT")" "dataset contract"
require_hash "${DATASET_ROOT}/dataset_receipt.json" "$(jq -r '.frozen_identities.dataset_receipt_sha256' "$EXPERIMENT")" "dataset receipt"
require_hash "$REMOTE_LOADER_RECEIPT" "$(jq -r '.frozen_identities.remote_loader_receipt_sha256' "$EXPERIMENT")" "remote loader receipt"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/preflight_groot_n17_pawn_dataset.py" "$(jq -r '.frozen_identities.remote_loader_preflight_script_sha256' "$EXPERIMENT")" "remote loader preflight script"
require_hash "$MODEL_SNAPSHOT_RECEIPT" "$(jq -r '.frozen_identities.model_snapshot_receipt_sha256' "$EXPERIMENT")" "model snapshot receipt"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/record_groot_n17_pawn_model_snapshots.py" "$(jq -r '.frozen_identities.model_snapshot_recorder_sha256' "$EXPERIMENT")" "snapshot recorder"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/patches/groot_n17_offline_processor_path.patch" "$(jq -r '.frozen_identities.offline_processor_patch_sha256' "$EXPERIMENT")" "offline processor patch"
require_hash "$PROCESSOR_FILE" "$(jq -r '.frozen_identities.patched_processor_file_sha256' "$EXPERIMENT")" "patched NVIDIA processor"
require_hash "${SIM2CLAW_ROOT}/configs/groot/sim2claw_so101_config.py" "$(jq -r '.frozen_identities.modality_config_sha256' "$EXPERIMENT")" "modality config"
require_hash "$FINETUNE_SCRIPT" "$(jq -r '.frozen_identities.nvidia_finetune_script_sha256' "$EXPERIMENT")" "NVIDIA finetune script"
require_hash "${GROOT_ROOT}/gr00t/experiment/launch_finetune.py" "$(jq -r '.frozen_identities.nvidia_launch_finetune_sha256' "$EXPERIMENT")" "NVIDIA finetune launcher"
require_hash "${GROOT_ROOT}/gr00t/configs/finetune_config.py" "$(jq -r '.frozen_identities.nvidia_finetune_config_sha256' "$EXPERIMENT")" "NVIDIA finetune config"

if [[ "$(git -C "$GROOT_ROOT" rev-parse HEAD)" != "$(jq -r '.frozen_identities.nvidia_source_commit' "$EXPERIMENT")" ]]; then
  echo "NVIDIA source commit drifted" >&2
  exit 1
fi
expected_dirty=$' M gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py'
actual_dirty="$(git -C "$GROOT_ROOT" status --porcelain=v1 --untracked-files=no)"
if [[ "$actual_dirty" != "$expected_dirty" ]]; then
  echo "NVIDIA tracked source dirtiness differs from the one frozen processor patch" >&2
  printf '%s\n' "$actual_dirty" >&2
  exit 1
fi
if [[ ! -x "$CUDA_HOME/bin/nvcc" || ! -x "$UV_BIN" ]]; then
  echo "required CUDA or uv executable is missing" >&2
  exit 1
fi
if [[ -e "$OUTPUT_ROOT" ]]; then
  echo "refusing to reuse pawn training output" >&2
  exit 1
fi
if [[ ! -f "$PROCESSOR_REF" ]] || [[ "$(<"$PROCESSOR_REF")" != "9ce19a195e423419c349abfc86fd07178b230561" ]]; then
  echo "offline processor cache ref is missing or drifted" >&2
  exit 1
fi
if [[ -e /home/shadeform/.cache/huggingface/token ]]; then
  echo "refusing training while a copied Hugging Face token remains on the worker" >&2
  exit 1
fi
if [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | tr -d '[:space:]')" ]]; then
  echo "GPU already has a compute process" >&2
  exit 1
fi

python3 - "$DATASET_ROOT" "$EXPERIMENT" "$REMOTE_LOADER_RECEIPT" "$MODEL_SNAPSHOT_RECEIPT" <<'PY'
import hashlib
import json
from pathlib import Path
import sys


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


dataset = Path(sys.argv[1])
experiment = json.loads(Path(sys.argv[2]).read_text())
loader = json.loads(Path(sys.argv[3]).read_text())
models = json.loads(Path(sys.argv[4]).read_text())
frozen = experiment["frozen_identities"]
receipt = json.loads((dataset / "dataset_receipt.json").read_text())
expected = receipt["payload_manifest"]
actual = {
    path.relative_to(dataset).as_posix()
    for path in dataset.rglob("*")
    if path.is_file() and path.name != "dataset_receipt.json"
}
if actual != set(expected):
    raise SystemExit("pawn dataset inventory drifted")
for relative, row in expected.items():
    path = dataset / relative
    if path.stat().st_size != int(row["size_bytes"]):
        raise SystemExit(f"pawn dataset size drifted: {relative}")
    if sha256_file(path) != row["sha256"]:
        raise SystemExit(f"pawn dataset hash drifted: {relative}")
if canonical_sha256(expected) != receipt["payload_manifest_sha256"]:
    raise SystemExit("pawn dataset manifest is internally inconsistent")
if receipt["payload_manifest_sha256"] != frozen["dataset_payload_manifest_sha256"]:
    raise SystemExit("pawn dataset manifest differs from the experiment")
if receipt["held_out_rows"] != 0 or not receipt["all_source_rows_evaluator_admitted"]:
    raise SystemExit("pawn dataset authority boundary drifted")

loader_expectations = {
    "passed": True,
    "dataset_unmodified_by_loader": True,
    "nvidia_source_dirty": False,
    "effective_start_count": 547,
    "action_target_slot_count": 8752,
    "action_scalar_count": 52512,
    "held_out_rows": 0,
    "model_queries": 0,
    "training_started": False,
}
for key, value in loader_expectations.items():
    if loader.get(key) != value:
        raise SystemExit(f"remote loader preflight drifted: {key}")
if loader["dataset_payload_manifest_sha256"] != frozen["dataset_payload_manifest_sha256"]:
    raise SystemExit("remote loader used a different dataset payload")
if loader["nvidia_commit"] != frozen["nvidia_source_commit"]:
    raise SystemExit("remote loader used a different NVIDIA commit")

receipt_copy = dict(models)
recorded_canonical = receipt_copy.pop("canonical_payload_sha256")
if canonical_sha256(receipt_copy) != recorded_canonical:
    raise SystemExit("model snapshot receipt canonical hash is invalid")
for name, expected_repo, expected_revision, expected_manifest in (
    (
        "base_model",
        "nvidia/GR00T-N1.7-3B",
        "2fc962b973bccdd5d8ce4f67cc63b264d6886495",
        frozen["base_model_inventory_sha256"],
    ),
    (
        "processor",
        "nvidia/Cosmos-Reason2-2B",
        "9ce19a195e423419c349abfc86fd07178b230561",
        frozen["processor_inventory_sha256"],
    ),
):
    model = models[name]
    if model["repo_id"] != expected_repo or model["revision"] != expected_revision:
        raise SystemExit(f"{name} repository or revision drifted")
    if model["inventory_sha256"] != expected_manifest:
        raise SystemExit(f"{name} inventory identity drifted")
    root = Path(model["path"])
    paths = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if not path.is_dir()
    }
    expected_rows = {row["path"]: row for row in model["inventory"]}
    if set(paths) != set(expected_rows):
        raise SystemExit(f"{name} inventory paths drifted")
    for relative, path in paths.items():
        row = expected_rows[relative]
        if path.is_symlink() != bool(row["is_symlink"]):
            raise SystemExit(f"{name} symlink type drifted: {relative}")
        target = path.readlink().as_posix() if path.is_symlink() else None
        if target != row["symlink_target"]:
            raise SystemExit(f"{name} symlink target drifted: {relative}")
        if path.stat().st_size != int(row["size_bytes"]):
            raise SystemExit(f"{name} size drifted: {relative}")
        if sha256_file(path) != row["sha256"]:
            raise SystemExit(f"{name} content drifted: {relative}")
    if canonical_sha256(model["inventory"]) != model["inventory_sha256"]:
        raise SystemExit(f"{name} inventory digest is internally inconsistent")
PY

cd "$GROOT_ROOT"
GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_ALBUMENTATIONS_UPDATE=1 \
  "$UV_BIN" run python - <<'PY'
from gr00t.model.gr00t_n1d7.processing_gr00t_n1d7 import build_processor

processor = build_processor("nvidia/Cosmos-Reason2-2B", {})
assert type(processor).__name__ == "Qwen3VLProcessor"
print("offline processor resolution passed")
PY

if [[ "${PAWN_GROOT_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  echo "pawn GR00T training launch preflight passed"
  exit 0
fi

install -d -m 755 "$EVIDENCE_ROOT"
mkdir "$OUTPUT_ROOT"
export SIM2CLAW_ROOT GROOT_ROOT DATASET_ROOT BASE_MODEL_PATH PROCESSOR_MODEL_PATH
export EVIDENCE_ROOT OUTPUT_ROOT EXPERIMENT_NAME EXPECTED_EXPERIMENT_SHA256
export CUDA_HOME PATH="$CUDA_HOME/bin:$PATH"
export CUDA_VISIBLE_DEVICES=0 NUM_GPUS=1 MAX_STEPS=1000 SAVE_STEPS=250
export USE_WANDB=0 GLOBAL_BATCH_SIZE=16 DATALOADER_NUM_WORKERS=4
export SHARD_SIZE=64 NUM_SHARDS_PER_EPOCH=9 EPISODE_SAMPLING_RATE=0.1
export GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_MODEL_PATH"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_ALBUMENTATIONS_UPDATE=1

python3 - "$EVIDENCE_ROOT/training-launch-receipt.json" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

payload = {
    "schema_version": "sim2claw.groot_n17_pawn_training_launch.v1",
    "experiment_sha256": os.environ["EXPECTED_EXPERIMENT_SHA256"],
    "task_id": "chess_pick_place_pawn_groot_100mm_v1",
    "workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
    "board_pose_id": "board_robotward_100mm_20260718_v3",
    "piece_layout_id": "two_sided_sparse_pawns_rows_1_2_7_8_v1",
    "training_case": "tan_pawn_c8_to_a6",
    "dataset_path": os.environ["DATASET_ROOT"],
    "base_model_path": os.environ["BASE_MODEL_PATH"],
    "processor_model_path": os.environ["PROCESSOR_MODEL_PATH"],
    "output_root": os.environ["OUTPUT_ROOT"],
    "experiment_name": os.environ["EXPERIMENT_NAME"],
    "maximum_steps": 1000,
    "save_steps": 250,
    "learning_rate": 0.00005,
    "state_dropout_probability": 0.0,
    "global_batch_size": 16,
    "episode_sampling_rate": 0.1,
    "shard_size": 64,
    "num_shards_per_epoch": 9,
    "nvidia_data_seed": 42,
    "held_out_rows_used": 0,
    "model_queries": 0,
    "training_started": True,
    "historical_72mm_authority": False,
    "physical_authority": False,
}
payload["canonical_payload_sha256"] = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

exec bash "$FINETUNE_SCRIPT" \
  --base-model-path "$BASE_MODEL_PATH" \
  --dataset-path "$DATASET_ROOT" \
  --modality-config-path "$SIM2CLAW_ROOT/configs/groot/sim2claw_so101_config.py" \
  --embodiment-tag NEW_EMBODIMENT \
  --output-dir "$OUTPUT_ROOT" \
  --experiment-name "$EXPERIMENT_NAME" \
  --state-dropout-prob 0.0 \
  --save-only-model \
  -- --learning_rate 5e-05
