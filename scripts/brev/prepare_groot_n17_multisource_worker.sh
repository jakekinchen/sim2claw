#!/usr/bin/env bash
set -euo pipefail

CODE_ARCHIVE="/home/shadeform/sim2claw-groot-multisource-code-0719.tgz"
DATASET_ARCHIVE="/home/shadeform/chess-manipulation-groot-multisource-v2.tgz"
CODE_ROOT="/home/shadeform/sim2claw-multisource"
CODE_ARCHIVE_SHA256="c5f0042257a908ba3f1f965e38be700707de47beb7d0ede29c03c799b0a64775"
DATASET_ARCHIVE_SHA256="7c6d47ab4df8766f58ebec9ccca7481881e2af4141f89f2b56028fc0db2e88b2"

verify_sha256() {
  local path="$1"
  local expected="$2"
  local actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    printf 'archive hash mismatch: %s\n' "$path" >&2
    exit 1
  fi
}

verify_sha256 "$CODE_ARCHIVE" "$CODE_ARCHIVE_SHA256"
verify_sha256 "$DATASET_ARCHIVE" "$DATASET_ARCHIVE_SHA256"
if [[ -e "$CODE_ROOT" || -e /home/shadeform/chess_manipulation_groot_multisource_v2 ]]; then
  echo "refusing to overwrite existing remote code or dataset" >&2
  exit 1
fi
mkdir "$CODE_ROOT"
tar -xzf "$CODE_ARCHIVE" -C "$CODE_ROOT"
tar -xzf "$DATASET_ARCHIVE" -C /home/shadeform
nvidia-smi \
  --query-gpu=name,uuid,memory.total,driver_version,compute_cap \
  --format=csv,noheader
sha256sum \
  "$CODE_ROOT/configs/tasks/chess_manipulation_groot_multisource_v2.json" \
  /home/shadeform/chess_manipulation_groot_multisource_v2/dataset_receipt.json
