#!/usr/bin/env bash
set -euo pipefail

TOKEN_FILE="${HF_TOKEN_FILE:-$HOME/.cache/huggingface/token}"
TOKEN="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"

if [ -z "$TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
  TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
fi

if [ -z "$TOKEN" ]; then
  echo "No Hugging Face token is available." >&2
  exit 2
fi

check_url() {
  local label="$1"
  local url="$2"
  local code

  code="$(curl -sS -L -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $TOKEN" "$url")"
  printf '%s http=%s\n' "$label" "$code"
  [ "$code" = "200" ]
}

check_url "hugging-face-account" "https://huggingface.co/api/whoami-v2" || {
  echo "The Hugging Face token is invalid or expired." >&2
  exit 2
}

check_url "groot-n1.7-config" \
  "https://huggingface.co/nvidia/GR00T-N1.7-3B/resolve/main/config.json" || {
  echo "GR00T N1.7 base-model access failed." >&2
  exit 2
}

check_url "cosmos-reason2-config" \
  "https://huggingface.co/nvidia/Cosmos-Reason2-2B/resolve/main/config.json" || {
  echo "The account lacks gated access to nvidia/Cosmos-Reason2-2B." >&2
  echo "Accept or obtain access on Hugging Face before provisioning paid compute." >&2
  exit 2
}

unset TOKEN
echo "GR00T N1.7 Hugging Face dependency access: PASS"
