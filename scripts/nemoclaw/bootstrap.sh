#!/usr/bin/env bash
set -euo pipefail

readonly UV_REQUIRED_VERSION="0.9.29"
REPO_ROOT="${SIM2CLAW_REPO_ROOT:-/sandbox/sim2claw}"
PROJECT="${SIM2CLAW_PROJECT:-configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json}"

cd "$REPO_ROOT"
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"

if ! command -v uv >/dev/null 2>&1; then
  printf 'bootstrap requires preinstalled uv %s; network installers are forbidden\n' \
    "$UV_REQUIRED_VERSION" >&2
  exit 1
fi
observed_uv_version="$(uv --version | awk 'NR == 1 {print $2}')"
if [[ "$observed_uv_version" != "$UV_REQUIRED_VERSION" ]]; then
  printf 'bootstrap requires uv %s, observed %s\n' \
    "$UV_REQUIRED_VERSION" "${observed_uv_version:-unknown}" >&2
  exit 1
fi

uv sync --locked --no-dev
mkdir -p /sandbox/.openclaw/workspace/skills/sim2claw
cp nemoclaw/skills/sim2claw/SKILL.md \
  /sandbox/.openclaw/workspace/skills/sim2claw/SKILL.md

uv run sim2claw doctor --target linux-cpu
uv run sim2claw project-inspect --project "$PROJECT"
uv run sim2claw pipeline-stage --project "$PROJECT" --stage inspect
