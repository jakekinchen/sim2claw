#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${SIM2CLAW_REPO_ROOT:-/sandbox/sim2claw}"
PORT="${SIM2CLAW_STUDIO_PORT:-4173}"
RUN_ROOT="$REPO_ROOT/runs/nemoclaw/studio"

cd "$REPO_ROOT"
mkdir -p "$RUN_ROOT"
export MUJOCO_GL="${MUJOCO_GL:-osmesa}"

python_exe="$(uv run python -c 'import sys; print(sys.executable)')"
python_real="$(readlink -f "$python_exe")"
readonly -a expected_argv=(
  "$python_exe" -m sim2claw.cli studio --read-only
  --host 0.0.0.0 --port "$PORT" --no-open
)

verify_pid_identity() {
  local pid="$1"
  local observed_exe
  local -a observed_argv=()
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  [[ -r "/proc/$pid/exe" && -r "/proc/$pid/cmdline" ]] || return 1
  observed_exe="$(readlink -f "/proc/$pid/exe")"
  [[ "$observed_exe" == "$python_real" ]] || return 1
  mapfile -d '' -t observed_argv <"/proc/$pid/cmdline"
  [[ "${#observed_argv[@]}" -eq "${#expected_argv[@]}" ]] || return 1
  local index
  for index in "${!expected_argv[@]}"; do
    [[ "${observed_argv[$index]}" == "${expected_argv[$index]}" ]] || return 1
  done
}

verify_read_only_health() {
  "$python_exe" - "http://127.0.0.1:$PORT/api/health" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=3) as response:
    payload = json.load(response)
expected = {
    "service": "sim2claw-studio",
    "read_only": True,
    "mode": "read_only_evidence",
    "recorder_control": "disabled",
    "physical_authority": False,
}
for key, value in expected.items():
    if payload.get(key) != value:
        raise SystemExit(
            f"Studio health {key} mismatch: expected {value!r}, observed {payload.get(key)!r}"
        )
PY
}

if [[ -f "$RUN_ROOT/studio.pid" ]]; then
  prior_pid="$(<"$RUN_ROOT/studio.pid")"
  if kill -0 "$prior_pid" 2>/dev/null; then
    if ! verify_pid_identity "$prior_pid"; then
      printf 'refusing stale or foreign Studio PID %s\n' "$prior_pid" >&2
      exit 1
    fi
    verify_read_only_health
    exit 0
  fi
  rm -f "$RUN_ROOT/studio.pid"
fi

nohup "${expected_argv[@]}" >"$RUN_ROOT/studio.log" 2>&1 &
studio_pid="$!"
printf '%s\n' "$studio_pid" >"$RUN_ROOT/studio.pid"

for _ in $(seq 1 30); do
  if ! verify_pid_identity "$studio_pid"; then
    printf 'Studio process identity changed or exited unexpectedly\n' >&2
    tail -80 "$RUN_ROOT/studio.log" >&2
    exit 1
  fi
  if verify_read_only_health 2>/dev/null; then
    verify_read_only_health
    exit 0
  fi
  sleep 1
done

printf 'Studio did not reach strict read-only health\n' >&2
tail -80 "$RUN_ROOT/studio.log" >&2
exit 1
