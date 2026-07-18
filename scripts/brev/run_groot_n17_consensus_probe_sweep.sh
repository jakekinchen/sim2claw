#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
EXPERIMENT="${EXPERIMENT:-${SIM2CLAW_ROOT}/configs/experiments/groot_n17_flow_consensus_v1.json}"
EXPECTED_EXPERIMENT_SHA256="${EXPECTED_EXPERIMENT_SHA256:-4558ccb360ecb58315c56d069b4836314a90ac488e6c848d2bd958d3106f4f8d}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/home/shadeform/runs/groot-n17-consensus/training-probes}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_PORT="${SERVER_PORT:-5555}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"

actual_experiment_sha256="$(sha256sum "${EXPERIMENT}" | awk '{print $1}')"
if [[ "${actual_experiment_sha256}" != "${EXPECTED_EXPERIMENT_SHA256}" ]]; then
  echo "flow-consensus experiment hash mismatch" >&2
  exit 1
fi

mkdir -p "${OUTPUT_ROOT}"
cd "${GROOT_DIR}"

while IFS= read -r arm; do
  arm_id="$(jq -r '.id' <<<"${arm}")"
  proposal_count="$(jq -r '.proposal_count' <<<"${arm}")"
  action_aggregation="$(jq -r '.action_aggregation' <<<"${arm}")"
  noise_scale="$(jq -r '.noise_scale' <<<"${arm}")"
  num_inference_timesteps="$(jq -r '.num_inference_timesteps' <<<"${arm}")"
  arm_root="${OUTPUT_ROOT}/${arm_id}"
  mkdir -p "${arm_root}"

  while IFS= read -r episode_index; do
    while IFS= read -r inference_seed; do
      output="${arm_root}/training-episode-${episode_index}-seed-${inference_seed}.json"
      log="${arm_root}/training-episode-${episode_index}-seed-${inference_seed}.log"
      if [[ -f "${output}" ]]; then
        echo "skipping completed arm=${arm_id} episode=${episode_index} seed=${inference_seed}"
        continue
      fi
      echo "probing arm=${arm_id} episode=${episode_index} seed=${inference_seed}"
      env \
        MUJOCO_GL=osmesa \
        PYOPENGL_PLATFORM=osmesa \
        PYTHONPATH="${SIM2CLAW_ROOT}/src" \
        "${UV_BIN}" run python \
          "${SIM2CLAW_ROOT}/scripts/brev/probe_groot_n17_seed_replay.py" \
          --episode-split training \
          --episode-index "${episode_index}" \
          --inference-seed "${inference_seed}" \
          --repeats 2 \
          --include-training-expert-diagnostic \
          --proposal-count "${proposal_count}" \
          --action-aggregation "${action_aggregation}" \
          --noise-scale "${noise_scale}" \
          --num-inference-timesteps "${num_inference_timesteps}" \
          --host "${SERVER_HOST}" \
          --port "${SERVER_PORT}" \
          >"${output}" 2>"${log}"
    done < <(jq -r '.row_zero_development_probe.inference_seeds[]' "${EXPERIMENT}")
  done < <(jq -r '.row_zero_development_probe.episode_indices[]' "${EXPERIMENT}")
done < <(jq -c '.row_zero_development_probe.candidate_arms[]' "${EXPERIMENT}")

env PYTHONPATH="${SIM2CLAW_ROOT}/src" "${UV_BIN}" run python \
  "${SIM2CLAW_ROOT}/scripts/analyze_groot_n17_consensus_sweep.py" \
  --experiment "${EXPERIMENT}" \
  --probe-root "${OUTPUT_ROOT}" \
  --output "${OUTPUT_ROOT}/summary.json"
