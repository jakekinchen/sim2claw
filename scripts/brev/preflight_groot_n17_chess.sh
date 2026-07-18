#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
DATASET_ROOT="${DATASET_ROOT:-$SIM2CLAW_ROOT/datasets/chess_pick_place_groot_v1}"
MODEL_ID="nvidia/GR00T-N1.7-3B"
MODEL_REVISION="2fc962b973bccdd5d8ce4f67cc63b264d6886495"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"

cd "$GROOT_ROOT"

"$UV_BIN" run python gr00t/data/stats.py \
  --dataset-path "$DATASET_ROOT" \
  --embodiment-tag NEW_EMBODIMENT \
  --modality-config-path "$SIM2CLAW_ROOT/configs/groot/sim2claw_so101_config.py"

env \
  SIM2CLAW_MODALITY_CONFIG="$SIM2CLAW_ROOT/configs/groot/sim2claw_so101_config.py" \
  DATASET_ROOT="$DATASET_ROOT" \
  MODEL_ID="$MODEL_ID" \
  MODEL_REVISION="$MODEL_REVISION" \
  "$UV_BIN" run python - <<'PY'
import importlib.util
import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download

config_path = Path(os.environ["SIM2CLAW_MODALITY_CONFIG"])
spec = importlib.util.spec_from_file_location("sim2claw_so101_config", config_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS
from gr00t.data.dataset.lerobot_episode_loader import LeRobotEpisodeLoader

configs = MODALITY_CONFIGS["new_embodiment"]
loader = LeRobotEpisodeLoader(os.environ["DATASET_ROOT"], configs)
first = loader[0]
model_path = snapshot_download(
    repo_id=os.environ["MODEL_ID"],
    revision=os.environ["MODEL_REVISION"],
)
print(
    json.dumps(
        {
            "dataset_episodes": len(loader),
            "first_episode_rows": len(first),
            "first_episode_columns": list(first.columns),
            "state_keys": configs["state"].modality_keys,
            "action_keys": configs["action"].modality_keys,
            "video_keys": configs["video"].modality_keys,
            "language_keys": configs["language"].modality_keys,
            "model_revision": os.environ["MODEL_REVISION"],
            "model_snapshot": model_path,
        },
        indent=2,
        sort_keys=True,
    )
)
PY
