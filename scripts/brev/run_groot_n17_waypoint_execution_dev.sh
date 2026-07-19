#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
PARENT_EXPERIMENT="${PARENT_EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_flow_consensus_v1.json}"
EXPECTED_PARENT_SHA256="${EXPECTED_PARENT_SHA256:-4558ccb360ecb58315c56d069b4836314a90ac488e6c848d2bd958d3106f4f8d}"
WAYPOINT_EXPERIMENT="${WAYPOINT_EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_waypoint_execution_v2.json}"
EXPECTED_WAYPOINT_SHA256="${EXPECTED_WAYPOINT_SHA256:-6fd12566e33c992994f74d7f68ab9a8c6b8796de9c7e4d5215658d99efc78b33}"
PROBE_SUMMARY="${PROBE_SUMMARY:-/home/shadeform/runs/groot-n17-consensus/training-probes/summary.json}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-consensus/waypoint-v2-development}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
CHECKPOINT_MANIFEST_SHA256="e89dae30e4b06af815b55e1a9e3036547eeae151463740e29f7fea8ad0b166ac"

if [[ "$(sha256sum "${PARENT_EXPERIMENT}" | awk '{print $1}')" != "${EXPECTED_PARENT_SHA256}" ]]; then
  echo "parent consensus experiment hash mismatch" >&2
  exit 1
fi
if [[ "$(sha256sum "${WAYPOINT_EXPERIMENT}" | awk '{print $1}')" != "${EXPECTED_WAYPOINT_SHA256}" ]]; then
  echo "waypoint experiment hash mismatch" >&2
  exit 1
fi
if [[ "$(jq -r '.promotion_authority' "${PROBE_SUMMARY}")" != "false" ]]; then
  echo "probe summary has invalid promotion authority" >&2
  exit 1
fi
if [[ "$(jq -r '.experiment_sha256' "${PROBE_SUMMARY}")" != "${EXPECTED_PARENT_SHA256}" ]]; then
  echo "probe summary references a different parent experiment" >&2
  exit 1
fi

mapfile -t candidate_arms < <(
  jq -r '.row_zero_development_probe.candidate_arms[] | select(.id | startswith("baseline-")) | .id' "${PARENT_EXPERIMENT}"
  jq -r '.nonbaseline_shortlist[]' "${PROBE_SUMMARY}"
)
maximum_candidate_arms="$(jq -r '.development.maximum_candidate_arms' "${WAYPOINT_EXPERIMENT}")"
if [[ "${#candidate_arms[@]}" -lt 2 || "${#candidate_arms[@]}" -gt "${maximum_candidate_arms}" ]]; then
  echo "waypoint candidate set violates the frozen size bound" >&2
  exit 1
fi

mkdir -p "${OUTPUT_ROOT}"
cd "${GROOT_DIR}"
for arm_id in "${candidate_arms[@]}"; do
  arm="$(jq -c --arg id "${arm_id}" '.row_zero_development_probe.candidate_arms[] | select(.id == $id)' "${PARENT_EXPERIMENT}")"
  if [[ -z "${arm}" ]]; then
    echo "development arm is not declared: ${arm_id}" >&2
    exit 1
  fi
  proposal_count="$(jq -r '.proposal_count' <<<"${arm}")"
  action_aggregation="$(jq -r '.action_aggregation' <<<"${arm}")"
  noise_scale="$(jq -r '.noise_scale' <<<"${arm}")"
  num_inference_timesteps="$(jq -r '.num_inference_timesteps' <<<"${arm}")"

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
          --checkpoint-id checkpoint-4000 \
          --checkpoint-manifest-sha256 "${CHECKPOINT_MANIFEST_SHA256}" \
          --proposal-count "${proposal_count}" \
          --action-aggregation "${action_aggregation}" \
          --noise-scale "${noise_scale}" \
          --num-inference-timesteps "${num_inference_timesteps}" \
          --physics-action-adapter "$(jq -r '.action_execution_adapter.method' "${WAYPOINT_EXPERIMENT}")" \
          --render-cadence "$(jq -r '.renderer.development_cadence' "${WAYPOINT_EXPERIMENT}")" \
          --execution-horizon "$(jq -r '.development.execution_horizon' "${WAYPOINT_EXPERIMENT}")" \
          --host "${SERVER_HOST}" \
          --port "${SERVER_PORT}" \
          --output "${output}" \
          >"${output}.log" 2>&1
    done < <(jq -r '.development.inference_seeds[]' "${WAYPOINT_EXPERIMENT}")
  done < <(jq -r '.development.episode_indices[]' "${WAYPOINT_EXPERIMENT}")
done

env PYTHONPATH="${SIM2CLAW_ROOT}/src" "${UV_BIN}" run python \
  "${SIM2CLAW_ROOT}/scripts/analyze_groot_n17_consensus_closed_loop.py" \
  --experiment "${PARENT_EXPERIMENT}" \
  --waypoint-experiment "${WAYPOINT_EXPERIMENT}" \
  --probe-summary "${PROBE_SUMMARY}" \
  --rollout-root "${OUTPUT_ROOT}" \
  --output "${OUTPUT_ROOT}/summary.json"
