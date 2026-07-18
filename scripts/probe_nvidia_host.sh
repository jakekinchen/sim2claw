#!/usr/bin/env bash
set -euo pipefail

uname -a
uname -m

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,uuid,memory.total,driver_version,compute_cap --format=csv,noheader
  nvidia-smi
else
  echo "nvidia-smi: unavailable"
fi

if [ -r /etc/nv_tegra_release ]; then
  sed -n '1,4p' /etc/nv_tegra_release
fi

if command -v nvcc >/dev/null 2>&1; then
  nvcc --version
else
  echo "nvcc: unavailable"
fi

if command -v free >/dev/null 2>&1; then
  free -h
fi

df -h /

if command -v python3 >/dev/null 2>&1; then
  python3 - <<'PY'
import json
import platform

payload = {
    "machine": platform.machine(),
    "platform": platform.platform(),
    "python": platform.python_version(),
}
try:
    import torch
except Exception as exc:
    payload["torch_import"] = f"failed: {type(exc).__name__}: {exc}"
else:
    payload.update(
        torch=torch.__version__,
        cuda_runtime=torch.version.cuda,
        cuda_available=torch.cuda.is_available(),
        cuda_device=(torch.cuda.get_device_name(0) if torch.cuda.is_available() else None),
    )
print(json.dumps(payload, indent=2, sort_keys=True))
PY
fi
