#!/usr/bin/env bash
set -euo pipefail

SIM2CLAW_ROOT="${SIM2CLAW_ROOT:-/home/shadeform/sim2claw}"
RUN_ROOT="${RUN_ROOT:-/home/shadeform/runs/groot-n17-recovery-candidate-a}"
EXPERIMENT_NAME="${EXPERIMENT_NAME:-sim2claw-groot-n17-recovery-5k}"
STEPS_TO_EVALUATE="${STEPS_TO_EVALUATE:-1000 2000 3000 4000 5000}"
SERVER_PORT="${SERVER_PORT:-5555}"
EVALUATION_ROOT="${EVALUATION_ROOT:-$RUN_ROOT/evaluation-v1}"
GROOT_DIR="${GROOT_DIR:-/home/shadeform/Isaac-GR00T}"
UV_BIN="${UV_BIN:-/home/shadeform/.local/bin/uv}"
RUNNER="$SIM2CLAW_ROOT/scripts/brev/run_groot_n17_chess_closed_loop.py"
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

for step in $STEPS_TO_EVALUATE; do
  checkpoint="$RUN_ROOT/checkpoints/$EXPERIMENT_NAME/checkpoint-$step"
  manifest="$RUN_ROOT/evaluation/checkpoint-$step/checkpoint-manifest.json"
  checkpoint_evaluation="$EVALUATION_ROOT/checkpoint-$step"
  test -d "$checkpoint"
  test -f "$manifest"
  mkdir -p "$checkpoint_evaluation/closed-loop"
  server_pid_file="$checkpoint_evaluation/policy-server.pid"
  CHECKPOINT_DIR="$checkpoint" \
  SERVER_LOG="$checkpoint_evaluation/policy-server.log" \
  SERVER_PID_FILE="$server_pid_file" \
  SERVER_PORT="$SERVER_PORT" \
  MAX_SERVER_SECONDS=3600 \
    bash "$SERVER_LAUNCHER"

  ready=0
  for _ in $(seq 1 180); do
    if python3 - "$SERVER_PORT" 2>/dev/null <<'PY'
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

  for episode_index in $(seq 0 3); do
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
  python3 - "$checkpoint_evaluation" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
receipts = [json.loads(path.read_text()) for path in sorted(root.glob("closed-loop/episode-*/receipt.json"))]
summary = {
    "schema_version": "sim2claw.groot_recovery_v1_regression_summary.v1",
    "episode_receipts": len(receipts),
    "passed": sum(int(bool(receipt["verdict"]["success"])) for receipt in receipts),
    "failed_gates": {
        gate: sum(int(not receipt["verdict"]["gates"][gate]["passed"]) for receipt in receipts)
        for gate in sorted(receipts[0]["verdict"]["gates"])
        if any(not receipt["verdict"]["gates"][gate]["passed"] for receipt in receipts)
    },
}
(root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps(summary, sort_keys=True))
PY
  cleanup_server
  server_pid_file=""
done
