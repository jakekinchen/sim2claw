#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${SIM2CLAW_REPO_ROOT:-/sandbox/sim2claw}"
PROJECT="${SIM2CLAW_PROJECT:-configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json}"
PORT="${SIM2CLAW_STUDIO_PORT:-4173}"
RECEIPT_ROOT="$REPO_ROOT/runs/nemoclaw/deployment"
RECEIPT="$RECEIPT_ROOT/deployment_receipt.json"
: "${SIM2CLAW_SOURCE_REVISION:?SIM2CLAW_SOURCE_REVISION is required}"
: "${SIM2CLAW_SOURCE_ARCHIVE_SHA256:?SIM2CLAW_SOURCE_ARCHIVE_SHA256 is required}"
: "${SIM2CLAW_PROJECT_BUNDLE_SHA256:?SIM2CLAW_PROJECT_BUNDLE_SHA256 is required}"

cd "$REPO_ROOT"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/sim2claw-deployment-verify.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

uv run sim2claw project-inspect --project "$PROJECT" >"$scratch/project.json"
uv run sim2claw pipeline-status --project "$PROJECT" >"$scratch/pipeline.json"
uv run python - "http://127.0.0.1:$PORT/api/health" "$scratch/health.json" <<'PY'
import json
import pathlib
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=3) as response:
    payload = json.load(response)
pathlib.Path(sys.argv[2]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

skill_sha256="$(sha256sum nemoclaw/skills/sim2claw/SKILL.md | awk '{print $1}')"

uv run python -m sim2claw.deployment_receipt \
  --output "$RECEIPT" \
  --project-path "$PROJECT" \
  --project-json "$scratch/project.json" \
  --pipeline-json "$scratch/pipeline.json" \
  --health-json "$scratch/health.json" \
  --skill-sha256 "$skill_sha256" \
  --source-revision "$SIM2CLAW_SOURCE_REVISION" \
  --source-archive-sha256 "$SIM2CLAW_SOURCE_ARCHIVE_SHA256" \
  --project-bundle-sha256 "$SIM2CLAW_PROJECT_BUNDLE_SHA256"

sha256sum "$RECEIPT" >"$RECEIPT.sha256"
