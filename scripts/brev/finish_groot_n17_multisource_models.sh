#!/usr/bin/env bash
set -euo pipefail

GROOT_ROOT="/home/shadeform/Isaac-GR00T"
UV_BIN="/home/shadeform/.local/bin/uv"
TOKEN_SOURCE="/home/shadeform/hf-token.tmp"
TOKEN_DESTINATION="/home/shadeform/.cache/huggingface/token"
BASE_DOWNLOAD="/home/shadeform/models/GR00T-N1.7-3B-2fc962b9"
PROCESSOR_PARTIAL="/home/shadeform/models/Cosmos-Reason2-2B-9ce19a19"
BASE_ROOT="/home/shadeform/model-snapshots/base/2fc962b973bccdd5d8ce4f67cc63b264d6886495"
PROCESSOR_ROOT="/home/shadeform/model-snapshots/processor/9ce19a195e423419c349abfc86fd07178b230561"

delete_token() {
  if [[ -f "$TOKEN_DESTINATION" ]]; then
    shred -u "$TOKEN_DESTINATION"
  fi
  if [[ -f "$TOKEN_SOURCE" ]]; then
    shred -u "$TOKEN_SOURCE"
  fi
}
trap delete_token EXIT

if [[ ! -s "$TOKEN_SOURCE" ]]; then
  echo "temporary Hugging Face token is missing" >&2
  exit 1
fi
if [[ ! -d "$BASE_DOWNLOAD" || -e "$BASE_ROOT" || -e "$PROCESSOR_ROOT" ]]; then
  echo "model staging state is not the expected one-time layout" >&2
  exit 1
fi
mkdir -p "$(dirname "$BASE_ROOT")" "$(dirname "$PROCESSOR_ROOT")"
mv "$BASE_DOWNLOAD" "$BASE_ROOT"
if [[ -e "$PROCESSOR_PARTIAL" ]]; then
  mv "$PROCESSOR_PARTIAL" "/home/shadeform/models/failed-gated-cosmos-partial"
fi
install -d -m 700 "$(dirname "$TOKEN_DESTINATION")"
install -m 600 "$TOKEN_SOURCE" "$TOKEN_DESTINATION"

cd "$GROOT_ROOT"
HF_HUB_DISABLE_TELEMETRY=1 "$UV_BIN" run hf download \
  nvidia/Cosmos-Reason2-2B \
  --revision 9ce19a195e423419c349abfc86fd07178b230561 \
  --local-dir "$PROCESSOR_ROOT"
delete_token
trap - EXIT

if [[ -d "$BASE_ROOT/.cache" ]]; then
  rm -r "$BASE_ROOT/.cache"
fi
if [[ -d "$PROCESSOR_ROOT/.cache" ]]; then
  rm -r "$PROCESSOR_ROOT/.cache"
fi
"$GROOT_ROOT/.venv/bin/python" \
  /home/shadeform/sim2claw-multisource/scripts/brev/record_groot_n17_pawn_model_snapshots.py \
  --base-model-path "$BASE_ROOT" \
  --processor-path "$PROCESSOR_ROOT" \
  --output /home/shadeform/groot-multisource-model-snapshots.json
test ! -e "$TOKEN_SOURCE"
test ! -e "$TOKEN_DESTINATION"
du -sh "$BASE_ROOT" "$PROCESSOR_ROOT"
