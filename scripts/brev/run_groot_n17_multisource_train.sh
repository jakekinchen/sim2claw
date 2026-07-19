#!/usr/bin/env bash
set -euo pipefail

SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw-multisource}"
GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
DATASET_ROOT="${DATASET_ROOT:-/home/shadeform/chess_manipulation_groot_multisource_v2}"
EXPERIMENT="${EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_multisource_v2.json}"
EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:?expected experiment hash is required}"
REMOTE_LOADER_RECEIPT="${REMOTE_LOADER_RECEIPT:-/home/shadeform/groot-multisource-remote-loader-preflight.json}"
MODEL_SNAPSHOT_RECEIPT="${MODEL_SNAPSHOT_RECEIPT:-/home/shadeform/groot-multisource-model-snapshots.json}"
BASE_MODEL_PATH="/home/shadeform/model-snapshots/base/2fc962b973bccdd5d8ce4f67cc63b264d6886495"
PROCESSOR_MODEL_PATH="/home/shadeform/model-snapshots/processor/9ce19a195e423419c349abfc86fd07178b230561"
EVIDENCE_ROOT="/home/shadeform/runs/groot-n17-multisource-v2"
OUTPUT_ROOT="${EVIDENCE_ROOT}/train"
EXPERIMENT_NAME="sim2claw-groot-n17-multisource-v2"
UV_BIN="/home/shadeform/.local/bin/uv"
CUDA_HOME="/usr/local/cuda-12.8"
TRAINING_WRAPPER="${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_multisource_train.sh"
TRAINING_LAUNCHER="${SIM2CLAW_ROOT}/scripts/brev/launch_groot_n17_multisource_train.sh"
FINETUNE_SCRIPT="${GROOT_ROOT}/examples/finetune.sh"
PROCESSOR_FILE="${GROOT_ROOT}/gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py"
BACKBONE_FILE="${GROOT_ROOT}/gr00t/model/modules/qwen3_backbone.py"

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
  echo "multisource experiment hash drifted" >&2
  exit 1
fi
if [[ "$(jq -r '.frozen_before_training' "$EXPERIMENT")" != "true" ]]; then
  echo "multisource experiment was not frozen before training" >&2
  exit 1
fi
if [[ "$(jq -r '.authority.training_cannot_promote' "$EXPERIMENT")" != "true" ]]; then
  echo "training authority boundary drifted" >&2
  exit 1
fi
if [[ "$(jq -r '.authority.physical_authority' "$EXPERIMENT")" != "false" ]]; then
  echo "multisource experiment gained physical authority" >&2
  exit 1
fi

require_hash "$TRAINING_WRAPPER" "$(jq -r '.frozen_identities.training_wrapper_sha256' "$EXPERIMENT")" "training wrapper"
require_hash "$TRAINING_LAUNCHER" "$(jq -r '.frozen_identities.training_launcher_sha256' "$EXPERIMENT")" "training launcher"
require_hash "${SIM2CLAW_ROOT}/configs/tasks/chess_manipulation_groot_multisource_v2.json" "$(jq -r '.frozen_identities.dataset_contract_sha256' "$EXPERIMENT")" "dataset contract"
require_hash "${DATASET_ROOT}/dataset_receipt.json" "$(jq -r '.frozen_identities.dataset_receipt_sha256' "$EXPERIMENT")" "dataset receipt"
require_hash "$REMOTE_LOADER_RECEIPT" "$(jq -r '.frozen_identities.remote_loader_receipt_sha256' "$EXPERIMENT")" "remote loader receipt"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/preflight_groot_n17_multisource_dataset.py" "$(jq -r '.frozen_identities.remote_loader_preflight_script_sha256' "$EXPERIMENT")" "remote loader preflight script"
require_hash "$MODEL_SNAPSHOT_RECEIPT" "$(jq -r '.frozen_identities.model_snapshot_receipt_sha256' "$EXPERIMENT")" "model snapshot receipt"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/record_groot_n17_pawn_model_snapshots.py" "$(jq -r '.frozen_identities.model_snapshot_recorder_sha256' "$EXPERIMENT")" "model snapshot recorder"
require_hash "${SIM2CLAW_ROOT}/scripts/brev/patches/groot_n17_multisource_offline_model_paths.patch" "$(jq -r '.frozen_identities.offline_model_paths_patch_sha256' "$EXPERIMENT")" "offline model paths patch"
require_hash "$PROCESSOR_FILE" "$(jq -r '.frozen_identities.patched_processor_file_sha256' "$EXPERIMENT")" "patched NVIDIA processor"
require_hash "$BACKBONE_FILE" "$(jq -r '.frozen_identities.patched_backbone_file_sha256' "$EXPERIMENT")" "patched NVIDIA backbone"
require_hash "${SIM2CLAW_ROOT}/configs/groot/sim2claw_so101_config.py" "$(jq -r '.frozen_identities.modality_config_sha256' "$EXPERIMENT")" "modality config"
require_hash "$FINETUNE_SCRIPT" "$(jq -r '.frozen_identities.nvidia_finetune_script_sha256' "$EXPERIMENT")" "NVIDIA finetune script"
require_hash "${GROOT_ROOT}/gr00t/experiment/launch_finetune.py" "$(jq -r '.frozen_identities.nvidia_launch_finetune_sha256' "$EXPERIMENT")" "NVIDIA finetune launcher"
require_hash "${GROOT_ROOT}/gr00t/configs/finetune_config.py" "$(jq -r '.frozen_identities.nvidia_finetune_config_sha256' "$EXPERIMENT")" "NVIDIA finetune config"

if [[ "$(git -C "$GROOT_ROOT" rev-parse HEAD)" != "$(jq -r '.frozen_identities.nvidia_source_commit' "$EXPERIMENT")" ]]; then
  echo "NVIDIA source commit drifted" >&2
  exit 1
fi
expected_dirty=$' M gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py\n M gr00t/model/modules/qwen3_backbone.py'
actual_dirty="$(git -C "$GROOT_ROOT" status --porcelain=v1 --untracked-files=no)"
if [[ "$actual_dirty" != "$expected_dirty" ]]; then
  echo "NVIDIA tracked source dirtiness differs from the frozen processor patch" >&2
  printf '%s\n' "$actual_dirty" >&2
  exit 1
fi
if [[ ! -x "$CUDA_HOME/bin/nvcc" || ! -x "$UV_BIN" ]]; then
  echo "required CUDA or uv executable is missing" >&2
  exit 1
fi
if [[ -e "$OUTPUT_ROOT" ]]; then
  echo "refusing to reuse multisource training output" >&2
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
    raise SystemExit("multisource dataset inventory drifted")
for relative, row in expected.items():
    path = dataset / relative
    if path.stat().st_size != int(row["size_bytes"]):
        raise SystemExit(f"multisource dataset size drifted: {relative}")
    if sha256_file(path) != row["sha256"]:
        raise SystemExit(f"multisource dataset hash drifted: {relative}")
if canonical_sha256(expected) != receipt["payload_manifest_sha256"]:
    raise SystemExit("multisource dataset manifest is internally inconsistent")
if receipt["payload_manifest_sha256"] != frozen["dataset_payload_manifest_sha256"]:
    raise SystemExit("multisource dataset manifest differs from the experiment")
for key, expected_value in (
    ("unique_source_episode_count", 73),
    ("derived_dataset_episode_count", 96),
    ("frame_count", 41088),
    ("task_count", 4),
    ("effective_h16_start_count", 39648),
    ("held_out_rows", 0),
    ("failed_action_rows", 0),
    ("physical_training_rows", 0),
    ("all_training_rows_evaluator_admitted", True),
    ("training_cannot_promote", True),
):
    if receipt.get(key) != expected_value:
        raise SystemExit(f"multisource dataset authority or count drifted: {key}")

loader_expectations = {
    "passed": True,
    "dataset_unmodified_by_loader": True,
    "nvidia_source_dirty": False,
    "episode_count": 96,
    "unique_source_episode_count": 73,
    "source_row_count": 41088,
    "effective_start_count": 39648,
    "action_target_slot_count": 634368,
    "action_scalar_count": 3806208,
    "shard_count": 310,
    "held_out_rows": 0,
    "failed_action_rows": 0,
    "physical_training_rows": 0,
    "model_queries": 0,
    "training_started": False,
}
for key, expected_value in loader_expectations.items():
    if loader.get(key) != expected_value:
        raise SystemExit(f"remote loader preflight drifted: {key}")
if loader["dataset_payload_manifest_sha256"] != frozen["dataset_payload_manifest_sha256"]:
    raise SystemExit("remote loader used a different dataset payload")
if loader["nvidia_commit"] != frozen["nvidia_source_commit"]:
    raise SystemExit("remote loader used a different NVIDIA commit")

models_copy = dict(models)
recorded_canonical = models_copy.pop("canonical_payload_sha256")
if canonical_sha256(models_copy) != recorded_canonical:
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
GROOT_BACKBONE_MODEL_PATH="$PROCESSOR_MODEL_PATH" \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_ALBUMENTATIONS_UPDATE=1 \
  "$UV_BIN" run python - <<'PY'
from gr00t.model.gr00t_n1d7.processing_gr00t_n1d7 import build_processor
from gr00t.model.modules.qwen3_backbone import Qwen3Backbone

processor = build_processor("nvidia/Cosmos-Reason2-2B", {"local_files_only": True})
assert type(processor).__name__ == "Qwen3VLProcessor"
print("offline processor resolution passed")
backbone = Qwen3Backbone(
    model_name="nvidia/Cosmos-Reason2-2B",
    select_layer=1,
    load_bf16=True,
    transformers_loading_kwargs={"local_files_only": True},
)
assert len(backbone.model.language_model.layers) == 1
print("offline backbone resolution passed")
PY

if [[ "${GROOT_MULTISOURCE_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  echo "multisource GR00T training launch preflight passed"
  exit 0
fi

install -d -m 755 "$EVIDENCE_ROOT"
mkdir "$OUTPUT_ROOT"
export SIM2CLAW_ROOT GROOT_ROOT DATASET_ROOT BASE_MODEL_PATH PROCESSOR_MODEL_PATH
export EVIDENCE_ROOT OUTPUT_ROOT EXPERIMENT_NAME EXPECTED_EXPERIMENT_SHA256
export CUDA_HOME PATH="$CUDA_HOME/bin:$PATH"
export CUDA_VISIBLE_DEVICES=0 NUM_GPUS=1 MAX_STEPS=1000 SAVE_STEPS=250
export USE_WANDB=0 GLOBAL_BATCH_SIZE=16 DATALOADER_NUM_WORKERS=4
export SHARD_SIZE=128 NUM_SHARDS_PER_EPOCH=64 EPISODE_SAMPLING_RATE=0.1
export GROOT_PROCESSOR_MODEL_PATH="$PROCESSOR_MODEL_PATH"
export GROOT_BACKBONE_MODEL_PATH="$PROCESSOR_MODEL_PATH"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_ALBUMENTATIONS_UPDATE=1

python3 - "$EVIDENCE_ROOT/training-launch-receipt.json" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

payload = {
    "schema_version": "sim2claw.groot_n17_multisource_training_launch.v1",
    "experiment_sha256": os.environ["EXPECTED_EXPERIMENT_SHA256"],
    "task_id": "chess_manipulation_groot_multisource_v2",
    "training_geometry_classes": [
        "photo_aligned_chess_workcell_v1_historical",
        "operator_updated_chess_workcell_v3_100mm",
    ],
    "current_workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
    "current_board_pose_id": "board_robotward_100mm_20260718_v3",
    "dataset_path": os.environ["DATASET_ROOT"],
    "base_model_path": os.environ["BASE_MODEL_PATH"],
    "processor_model_path": os.environ["PROCESSOR_MODEL_PATH"],
    "output_root": os.environ["OUTPUT_ROOT"],
    "experiment_name": os.environ["EXPERIMENT_NAME"],
    "maximum_steps": 1000,
    "save_steps": 250,
    "learning_rate": 0.00005,
    "state_dropout_probability": 0.1,
    "global_batch_size": 16,
    "episode_sampling_rate": 0.1,
    "shard_size": 128,
    "num_shards_per_epoch": 64,
    "nvidia_data_seed": 42,
    "unique_source_episode_count": 73,
    "derived_dataset_episode_count": 96,
    "held_out_rows_used": 0,
    "failed_action_rows_used": 0,
    "physical_training_rows": 0,
    "training_started": True,
    "training_cannot_promote": True,
    "physical_authority": False,
}
payload["canonical_payload_sha256"] = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

exec "$UV_BIN" run bash "$FINETUNE_SCRIPT" \
  --base-model-path "$BASE_MODEL_PATH" \
  --dataset-path "$DATASET_ROOT" \
  --modality-config-path "$SIM2CLAW_ROOT/configs/groot/sim2claw_so101_config.py" \
  --embodiment-tag NEW_EMBODIMENT \
  --output-dir "$OUTPUT_ROOT" \
  --experiment-name "$EXPERIMENT_NAME" \
  --state-dropout-prob 0.1 \
  --save-only-model \
  -- --learning_rate 5e-05
