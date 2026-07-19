#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
EXPERIMENT="${EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_flow_consensus_v1.json}"
EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:-4558ccb360ecb58315c56d069b4836314a90ac488e6c848d2bd958d3106f4f8d}"
PROBE_SUMMARY="${PROBE_SUMMARY:-/home/shadeform/runs/groot-n17-consensus/training-probes/summary.json}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-consensus/training-closed-loop}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
CHECKPOINT_MANIFEST_SHA256="e89dae30e4b06af815b55e1a9e3036547eeae151463740e29f7fea8ad0b166ac"

actual_experiment_sha256="$(sha256sum "${EXPERIMENT}" | awk '{print $1}')"
if [[ "${actual_experiment_sha256}" != "${EXPECTED_EXPERIMENT_SHA256}" ]]; then
  echo "flow-consensus experiment hash mismatch" >&2
  exit 1
fi
if [[ "$(jq -r '.promotion_authority' "${PROBE_SUMMARY}")" != "false" ]]; then
  echo "probe summary has invalid promotion authority" >&2
  exit 1
fi
if [[ "$(jq -r '.experiment_sha256' "${PROBE_SUMMARY}")" != "${EXPECTED_EXPERIMENT_SHA256}" ]]; then
  echo "probe summary references a different experiment" >&2
  exit 1
fi

mkdir -p "${OUTPUT_ROOT}"
cd "${GROOT_DIR}"
while IFS= read -r arm_id; do
  arm="$(jq -c --arg id "${arm_id}" '.row_zero_development_probe.candidate_arms[] | select(.id == $id)' "${EXPERIMENT}")"
  if [[ -z "${arm}" ]]; then
    echo "shortlisted arm is not declared: ${arm_id}" >&2
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
          --execution-horizon "$(jq -r '.invariants.execution_horizon' "${EXPERIMENT}")" \
          --host "${SERVER_HOST}" \
          --port "${SERVER_PORT}" \
          --output "${output}" \
          >"${output}.log" 2>&1
    done < <(jq -r '.closed_loop_development.inference_seeds[]' "${EXPERIMENT}")
  done < <(jq -r '.closed_loop_development.episode_indices[]' "${EXPERIMENT}")
done < <(jq -r '.nonbaseline_shortlist[]' "${PROBE_SUMMARY}")

env PYTHONPATH="${SIM2CLAW_ROOT}/src" "${UV_BIN}" run python \
  "${SIM2CLAW_ROOT}/scripts/analyze_groot_n17_consensus_closed_loop.py" \
  --experiment "${EXPERIMENT}" \
  --probe-summary "${PROBE_SUMMARY}" \
  --rollout-root "${OUTPUT_ROOT}" \
  --output "${OUTPUT_ROOT}/summary.json"
