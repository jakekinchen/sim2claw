#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="/home/shadeform/Isaac-GR00T"
UV_BIN="/home/shadeform/.local/bin/uv"
MODEL_ROOT="/home/shadeform/models"
BASE_ROOT="$MODEL_ROOT/GR00T-N1.7-3B-2fc962b9"
PROCESSOR_ROOT="$MODEL_ROOT/Cosmos-Reason2-2B-9ce19a19"

if [[ -e "$BASE_ROOT" || -e "$PROCESSOR_ROOT" ]]; then
  echo "refusing to reuse a model snapshot destination" >&2
  exit 1
fi
mkdir -p "$MODEL_ROOT"
cd "$GROOT_ROOT"
HF_HUB_DISABLE_TELEMETRY=1 "$UV_BIN" run hf download \
  nvidia/GR00T-N1.7-3B \
  --revision 2fc962b973bccdd5d8ce4f67cc63b264d6886495 \
  --local-dir "$BASE_ROOT"
HF_HUB_DISABLE_TELEMETRY=1 "$UV_BIN" run hf download \
  nvidia/Cosmos-Reason2-2B \
  --revision 9ce19a195e423419c349abfc86fd07178b230561 \
  --local-dir "$PROCESSOR_ROOT"

find "$BASE_ROOT" "$PROCESSOR_ROOT" -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > /home/shadeform/groot-multisource-model-files.sha256
du -sh "$BASE_ROOT" "$PROCESSOR_ROOT"
