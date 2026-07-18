#!/usr/bin/env bash
# Control SO-101 teleop on the Jetson from this Mac over SSH.
# Usage: ./mac-teleop.sh {start|stop|status}
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SIM2CLAW_JETSON_ENV:-$SCRIPT_DIR/local.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  set -a
  source "$ENV_FILE"
  set +a
fi

JETSON_USER="${JETSON_USER:?Set JETSON_USER in $ENV_FILE or the environment}"
JETSON_HOST="${JETSON_HOST:?Set JETSON_HOST in $ENV_FILE or the environment}"
REMOTE_TOGGLE="${REMOTE_TOGGLE:-~/.local/bin/so101-teleop-toggle}"
PID_FILE="${PID_FILE:-~/.cache/so101-teleop.pid}"

ssh_run() {
  local remote_command="$1"
  local ssh_base=(
    ssh
    -o StrictHostKeyChecking=accept-new
    -o ConnectTimeout=8
  )

  if [[ -n "${JETSON_PASSWORD:-}" ]]; then
    if command -v sshpass >/dev/null 2>&1; then
      sshpass -p "$JETSON_PASSWORD" "${ssh_base[@]}" \
        -o PreferredAuthentications=password -o PubkeyAuthentication=no \
        "${JETSON_USER}@${JETSON_HOST}" "$remote_command"
      return $?
    fi

    JETSON_PASSWORD="$JETSON_PASSWORD" /usr/bin/expect -f - \
      "$JETSON_USER" "$JETSON_HOST" "$remote_command" <<'EOF'
set user [lindex $argv 0]
set host [lindex $argv 1]
set command [lindex $argv 2]
set timeout 30
log_user 0
spawn ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 "$user@$host" "$command"
expect {
  -re "(?i)password:" { send "$env(JETSON_PASSWORD)\r"; exp_continue }
  eof
}
set result [wait]
exit [lindex $result 3]
EOF
    return $?
  fi

  "${ssh_base[@]}" "${JETSON_USER}@${JETSON_HOST}" "$remote_command"
}

remote_is_running() {
  ssh_run "PID=\$(cat ${PID_FILE} 2>/dev/null || true); test -n \"\$PID\" && kill -0 \"\$PID\" 2>/dev/null" >/dev/null 2>&1
}

case "${1:-status}" in
  start)
    if remote_is_running; then
      echo "Teleop already running."
    else
      ssh_run "${REMOTE_TOGGLE}" >/dev/null 2>&1
      sleep 2
      if remote_is_running; then echo "Teleop STARTED."; else echo "Failed to start (check Jetson log)."; fi
    fi
    ;;
  stop)
    ssh_run "PID=\$(cat ${PID_FILE} 2>/dev/null || true); \
      if [ -n \"\$PID\" ]; then kill -INT \"\$PID\" 2>/dev/null || true; fi; \
      sleep 1; \
      pkill -TERM -f '[l]erobot-teleoperate' 2>/dev/null || true; \
      sleep 1; \
      pkill -KILL -f '[l]erobot-teleoperate' 2>/dev/null || true; \
      rm -f ${PID_FILE}" >/dev/null 2>&1
    sleep 1
    if remote_is_running; then
      echo "Failed to stop teleop."
      exit 1
    fi
    echo "Teleop STOPPED."
    ;;
  status)
    if remote_is_running; then echo "RUNNING"; else echo "STOPPED"; fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
