#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
EXPERIMENT="${EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_rate_limited_temporal_v4.json}"
EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:-3a6419d905fd29de4f61f931181d414de531d466c722f13dbf0cf2a39f2aab05}"
PARENT_SUMMARY="${PARENT_SUMMARY:-/home/shadeform/runs/groot-n17-consensus/temporal-v3-development/summary.json}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-consensus/rate-limited-v4-development}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"

if [[ "$(sha256sum "${EXPERIMENT}" | awk '{print $1}')" != "${EXPECTED_EXPERIMENT_SHA256}" ]]; then
  echo "rate-limited temporal experiment hash mismatch" >&2
  exit 1
fi
if [[ "$(sha256sum "${PARENT_SUMMARY}" | awk '{print $1}')" != "$(jq -r '.parent_temporal_summary_sha256' "${EXPERIMENT}")" ]]; then
  echo "parent temporal summary hash mismatch" >&2
  exit 1
fi
if [[ "$(jq -r '.held_out_may_open' "${PARENT_SUMMARY}")" != "false" ]]; then
  echo "parent temporal summary unexpectedly opened held-out" >&2
  exit 1
fi

mapfile -t action_rate_limits < <(
  jq -r '.rate_limiter.maximum_abs_delta_per_sample[]' "${EXPERIMENT}"
)
arm_id="$(jq -r '.development.arm_id' "${EXPERIMENT}")"
mkdir -p "${OUTPUT_ROOT}"
cd "${GROOT_DIR}"
while IFS= read -r episode_index; do
  while IFS= read -r inference_seed; do
    output="${OUTPUT_ROOT}/${arm_id}/training-episode-${episode_index}-seed-${inference_seed}"
    if [[ -f "${output}/receipt.json" ]]; then
      echo "skipping completed arm=${arm_id} episode=${episode_index} seed=${inference_seed}"
      continue
    fi
    mkdir -p "$(dirname "${output}")"
    echo "evaluating arm=${arm_id} episode=${episode_index} seed=${inference_seed}"
    env \
      MUJOCO_GL=osmesa \
      PYOPENGL_PLATFORM=osmesa \
      PYTHONPATH="${SIM2CLAW_ROOT}/src" \
      "${UV_BIN}" run python \
        "${SIM2CLAW_ROOT}/scripts/brev/run_groot_n17_chess_closed_loop.py" \
        --episode-split training \
        --episode-index "${episode_index}" \
        --inference-seed "${inference_seed}" \
        --rollout-replicate 0 \
        --policy-server-mode seeded_reset \
        --checkpoint-id "$(jq -r '.frozen_identities.nominal_checkpoint_id' "${EXPERIMENT}")" \
        --checkpoint-manifest-sha256 "$(jq -r '.frozen_identities.nominal_checkpoint_aggregate_manifest_sha256' "${EXPERIMENT}")" \
        --proposal-count "$(jq -r '.fixed_model_inference.proposal_count' "${EXPERIMENT}")" \
        --action-aggregation "$(jq -r '.fixed_model_inference.action_aggregation' "${EXPERIMENT}")" \
        --noise-scale "$(jq -r '.fixed_model_inference.noise_scale' "${EXPERIMENT}")" \
        --num-inference-timesteps "$(jq -r '.fixed_model_inference.num_inference_timesteps' "${EXPERIMENT}")" \
        --physics-action-adapter "$(jq -r '.action_execution_adapter.method' "${EXPERIMENT}")" \
        --render-cadence "$(jq -r '.renderer.development_cadence' "${EXPERIMENT}")" \
        --execution-horizon "$(jq -r '.fixed_temporal_executor.execution_horizon' "${EXPERIMENT}")" \
        --temporal-action-aggregation "$(jq -r '.fixed_temporal_executor.temporal_action_aggregation' "${EXPERIMENT}")" \
        --temporal-decay "$(jq -r '.fixed_temporal_executor.temporal_decay' "${EXPERIMENT}")" \
        --action-rate-limits "${action_rate_limits[@]}" \
        --action-rate-limit-source "$(jq -r '.rate_limiter.source' "${EXPERIMENT}")" \
        --host "${SERVER_HOST}" \
        --port "${SERVER_PORT}" \
        --output "${output}" \
        >"${output}.log" 2>&1
  done < <(jq -r '.development.inference_seeds[]' "${EXPERIMENT}")
done < <(jq -r '.development.episode_indices[]' "${EXPERIMENT}")

env PYTHONPATH="${SIM2CLAW_ROOT}/src" "${UV_BIN}" run python \
  "${SIM2CLAW_ROOT}/scripts/analyze_groot_n17_rate_limited_temporal.py" \
  --experiment "${EXPERIMENT}" \
  --parent-summary "${PARENT_SUMMARY}" \
  --rollout-root "${OUTPUT_ROOT}" \
  --output "${OUTPUT_ROOT}/summary.json"
