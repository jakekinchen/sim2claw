#!/usr/bin/env bash
set -euo pipefail

GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
RUN_ROOT="${RUN_ROOT:-/home/shadeform/runs/groot-n17-recovery-candidate-a}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-recovery-5k}"
HELD_OUT_DATASET="${HELD_OUT_DATASET:-$SIM2CLAW_ROOT/datasets/chess_pick_place_groot_recovery_v2_held_out}"
STEPS_TO_EVALUATE="${STEPS_TO_EVALUATE:-1000 2000 3000 4000 5000}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
SERVER_PORT="${SERVER_PORT:-5555}"
EVALUATION_ROOT="${EVALUATION_ROOT:-$RUN_ROOT/evaluation}"
RUNNER="$SIM2CLAW_ROOT/scripts/brev/run_groot_n17_recovery_closed_loop.py"
SERVER_LAUNCHER="$SIM2CLAW_ROOT/scripts/brev/launch_groot_n17_chess_server.sh"

mkdir -p "$EVALUATION_ROOT"
server_pid_file=""

cleanup_server() {
  if [[ -n "$server_pid_file" && -f "$server_pid_file" ]]; then
    server_pid="$(cat "$server_pid_file")"
    if kill -0 "$server_pid" 2>/dev/null; then
      kill "$server_pid" 2>/dev/null || true
      for _ in $(seq 1 30); do
        if ! kill -0 "$server_pid" 2>/dev/null; then
          break
        fi
        sleep 1
      done
      if kill -0 "$server_pid" 2>/dev/null; then
        kill -KILL "$server_pid" 2>/dev/null || true
      fi
    fi
    rm -f "$server_pid_file"
  fi
}
trap cleanup_server EXIT INT TERM

write_checkpoint_manifest() {
  checkpoint="$1"
  step="$2"
  manifest="$3"
  python3 - "$checkpoint" "$step" "$manifest" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

checkpoint = Path(sys.argv[1]).resolve()
step = int(sys.argv[2])
output = Path(sys.argv[3])
names = [
    *sorted(path.name for path in checkpoint.glob("model*.safetensors")),
    "model.safetensors.index.json",
    "config.json",
    "processor_config.json",
    "statistics.json",
    "trainer_state.json",
]
files = {}
for name in names:
    path = checkpoint / name
    if not path.is_file():
        raise SystemExit(f"checkpoint identity file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    files[name] = digest.hexdigest()
payload = {
    "schema_version": "sim2claw.groot_checkpoint_manifest.v1",
    "checkpoint_step": step,
    "checkpoint_path": str(checkpoint),
    "files": files,
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
}

summarize_checkpoint() {
  checkpoint_evaluation="$1"
  python3 - "$checkpoint_evaluation" <<'PY'
import collections
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
receipts = [json.loads(path.read_text()) for path in sorted(root.glob("closed-loop/episode-*/receipt.json"))]
families = collections.defaultdict(lambda: {"passed": 0, "total": 0})
failed_gates = collections.Counter()
for receipt in receipts:
    family = receipt["perturbation"]["family"]
    families[family]["total"] += 1
    families[family]["passed"] += int(bool(receipt["verdict"]["success"]))
    for gate, result in receipt["verdict"]["gates"].items():
        if not result["passed"]:
            failed_gates[gate] += 1
summary = {
    "schema_version": "sim2claw.groot_recovery_checkpoint_summary.v1",
    "episode_receipts": len(receipts),
    "passed": sum(int(bool(receipt["verdict"]["success"])) for receipt in receipts),
    "families": dict(sorted(families.items())),
    "failed_gates": dict(failed_gates.most_common()),
}
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
PY
}

for step in $STEPS_TO_EVALUATE; do
  checkpoint="$RUN_ROOT/checkpoints/$EXPERIMENT_NAME/checkpoint-$step"
  checkpoint_evaluation="$EVALUATION_ROOT/checkpoint-$step"
  manifest="$checkpoint_evaluation/checkpoint-manifest.json"
  if [[ ! -d "$checkpoint" ]]; then
    echo "checkpoint missing: $checkpoint" >&2
    exit 1
  fi
  mkdir -p "$checkpoint_evaluation/open-loop" "$checkpoint_evaluation/closed-loop"
  write_checkpoint_manifest "$checkpoint" "$step" "$manifest"

  cd "$GROOT_DIR"
  "$UV_BIN" run python gr00t/eval/open_loop_eval.py \
    --dataset-path "$HELD_OUT_DATASET" \
    --embodiment-tag new_embodiment \
    --model-path "$checkpoint" \
    --traj-ids 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 \
    --steps 363 \
    --action-horizon 16 \
    >"$checkpoint_evaluation/open-loop/non-contact.log" 2>&1
  "$UV_BIN" run python gr00t/eval/open_loop_eval.py \
    --dataset-path "$HELD_OUT_DATASET" \
    --embodiment-tag new_embodiment \
    --model-path "$checkpoint" \
    --traj-ids 18 19 20 21 22 23 \
    --steps 485 \
    --action-horizon 16 \
    >"$checkpoint_evaluation/open-loop/contact-recovery.log" 2>&1

  server_pid_file="$checkpoint_evaluation/policy-server.pid"
  CHECKPOINT_DIR="$checkpoint" \
  SERVER_LOG="$checkpoint_evaluation/policy-server.log" \
  SERVER_PID_FILE="$server_pid_file" \
  SERVER_PORT="$SERVER_PORT" \
  MAX_SERVER_SECONDS=7200 \
    bash "$SERVER_LAUNCHER"

  ready=0
  for _ in $(seq 1 180); do
    if python3 - "$SERVER_PORT" <<'PY'
import socket
import sys
with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=1):
    pass
PY
    then
      ready=1
      break
    fi
    if ! kill -0 "$(cat "$server_pid_file")" 2>/dev/null; then
      break
    fi
    sleep 2
  done
  if [[ "$ready" != 1 ]]; then
    echo "policy server failed to become ready for checkpoint-$step" >&2
    tail -n 120 "$checkpoint_evaluation/policy-server.log" >&2
    exit 1
  fi

  for episode_index in $(seq 0 23); do
    episode_name="$(printf 'episode-%02d' "$episode_index")"
    episode_output="$checkpoint_evaluation/closed-loop/$episode_name"
    if [[ -f "$episode_output/receipt.json" ]]; then
      continue
    fi
    if [[ -e "$episode_output" ]]; then
      mv "$episode_output" "$episode_output.failed-$(date -u +%Y%m%dT%H%M%SZ)"
    fi
    cd "$GROOT_DIR"
    PYTHONPATH="$SIM2CLAW_ROOT/src" \
    MUJOCO_GL=egl \
    PYOPENGL_PLATFORM=egl \
      "$UV_BIN" run python "$RUNNER" \
        --episode-index "$episode_index" \
        --checkpoint-manifest "$manifest" \
        --port "$SERVER_PORT" \
        --output "$episode_output" \
        >"$checkpoint_evaluation/closed-loop/$episode_name.log" 2>&1
  done
  summarize_checkpoint "$checkpoint_evaluation"
  cleanup_server
  server_pid_file=""
done
