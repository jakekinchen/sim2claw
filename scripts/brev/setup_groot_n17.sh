#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="${GROOT_ROOT:-/home/shadeform/Isaac-GR00T}"
EXPECTED_COMMIT="23ace64f17aa5015259b8609d371eb61a357c776"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  cuda-nvcc-12-8 \
  ffmpeg \
  git-lfs \
  libosmesa6
git lfs install --skip-repo

if [ ! -d "$GROOT_ROOT/.git" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git clone \
    --depth 1 \
    --branch n1.7-release \
    --recurse-submodules \
    --shallow-submodules \
    https://github.com/NVIDIA/Isaac-GR00T.git \
    "$GROOT_ROOT"
fi

actual_commit="$(git -C "$GROOT_ROOT" rev-parse HEAD)"
if [ "$actual_commit" != "$EXPECTED_COMMIT" ]; then
  echo "unexpected Isaac-GR00T commit: $actual_commit" >&2
  exit 1
fi

cd "$GROOT_ROOT"
git lfs pull --include="scripts/deployment/dgpu/wheels/*"
if [ ! -x "$UV_BIN" ]; then
  echo "uv executable missing: $UV_BIN" >&2
  exit 1
fi
"$UV_BIN" sync --python 3.10
"$UV_BIN" pip install --python .venv/bin/python mujoco==3.10.0

"$UV_BIN" run python - <<'PY'
import json
import subprocess

import torch

payload = {
    "torch": torch.__version__,
    "cuda_runtime": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
    "gr00t_import": False,
}
import gr00t
payload["gr00t_import"] = True
payload["source_commit"] = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True
).strip()
print(json.dumps(payload, indent=2, sort_keys=True))
if not torch.cuda.is_available():
    raise SystemExit("CUDA unavailable")
PY

nvidia-smi --query-gpu=name,uuid,memory.total,driver_version,compute_cap --format=csv,noheader
ffmpeg -version | head -n 1
dpkg-query -W -f='libosmesa6=${Version}\n' libosmesa6
