#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run-codex-pair-cycle.sh --once [options]
  run-codex-pair-cycle.sh --loop [options]
  run-codex-pair-cycle.sh --dry-run [options]

Options:
  --root <dir>          Target repo. Default: current directory.
  --interval <seconds>  Delay between loop cycles. Default: 60.
  --max-cycles <n>      Maximum loop cycles. Default: 1 for --once, 10 for --loop.
  --model <name>        Pass a model to codex exec.
  --sandbox <mode>      Codex sandbox mode. Default: workspace-write.
  --allow-dirty         Allow starting from a dirty worktree.
  -h, --help            Show this help.

The loop continues only when the read-only Reviewer returns CONTINUE.
Any STOP, ESCALATE, REDIRECT, NUDGE, missing decision, command failure, or stop
sentinel ends the loop.
EOF
}

ROOT="$PWD"
MODE=""
INTERVAL="60"
MAX_CYCLES=""
MODEL=""
SANDBOX="workspace-write"
ALLOW_DIRTY=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once)
      MODE="once"
      shift
      ;;
    --loop)
      MODE="loop"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --root)
      ROOT="${2:?--root requires a directory}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:?--interval requires seconds}"
      shift 2
      ;;
    --max-cycles)
      MAX_CYCLES="${2:?--max-cycles requires a number}"
      shift 2
      ;;
    --model)
      MODEL="${2:?--model requires a value}"
      shift 2
      ;;
    --sandbox)
      SANDBOX="${2:?--sandbox requires a value}"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$MODE" ]; then
  usage >&2
  exit 2
fi

if [ "$MODE" = "once" ] || [ "$MODE" = "dry-run" ]; then
  MAX_CYCLES="${MAX_CYCLES:-1}"
else
  MAX_CYCLES="${MAX_CYCLES:-10}"
fi

ROOT="$(cd "$ROOT" && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'Not a git repo: %s\n' "$ROOT" >&2
  exit 1
fi

if [ ! -f GOAL.md ]; then
  printf 'GOAL.md missing. Run bootstrap and fill GOAL.md before starting the loop.\n' >&2
  exit 1
fi

if ! command -v codex >/dev/null 2>&1 && [ "$MODE" != "dry-run" ]; then
  printf 'codex CLI not found on PATH.\n' >&2
  exit 1
fi

repo_slug="$(basename "$ROOT" | tr -cs 'a-zA-Z0-9._-' '-')"
runtime_dir="/tmp/autonomous-project-workflow/$repo_slug"
mkdir -p "$runtime_dir"

lock_dir="$ROOT/.autonomous-workflow.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  printf 'Another autonomous workflow cycle appears to be running: %s\n' "$lock_dir" >&2
  exit 1
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

has_stop_sentinel() {
  grep -q '<stop-orchestrator/>' GOAL.md 2>/dev/null
}

latest_reviewer_decision() {
  file="$(
    find "$runtime_dir" -maxdepth 1 -type f \
      -name '*-reviewer-last-message.md' -print | sort | tail -1
  )"
  if [ -z "${file:-}" ]; then
    return 1
  fi
  grep -E '^[[:space:]]*(CONTINUE|NUDGE|REDIRECT|STOP|ESCALATE)[[:space:]]*$' "$file" |
    head -1 |
    tr -d '[:space:]'
}

ensure_clean_start() {
  if [ "$ALLOW_DIRTY" -eq 1 ]; then
    return
  fi
  if [ -n "$(git status --porcelain)" ]; then
    printf 'Refusing to start from a dirty worktree. Commit/stash changes or pass --allow-dirty.\n' >&2
    git status --short >&2
    exit 1
  fi
}

codex_base_args() {
  role="$1"
  printf '%s\n' "exec"
  printf '%s\n' "--json"
  printf '%s\n' "--ephemeral"
  printf '%s\n' "-C"
  printf '%s\n' "$ROOT"
  if [ -n "$MODEL" ]; then
    printf '%s\n' "-m"
    printf '%s\n' "$MODEL"
  fi
  printf '%s\n' "-s"
  if [ "$role" = "reviewer" ]; then
    printf '%s\n' "read-only"
  else
    printf '%s\n' "$SANDBOX"
  fi
}

run_role() {
  role="$1"
  prompt_file="$2"
  stamp="$(date +%Y%m%d%H%M%S)"
  json_log="$runtime_dir/$stamp-$role.jsonl"
  last_msg="$runtime_dir/$stamp-$role-last-message.md"

  if [ "$MODE" = "dry-run" ]; then
    printf '\n[dry-run] would run %s role\n' "$role"
    printf '[dry-run] prompt: %s\n' "$prompt_file"
    printf '[dry-run] log: %s\n' "$json_log"
    return
  fi

  args=()
  while IFS= read -r argument; do
    args+=("$argument")
  done < <(codex_base_args "$role")
  args+=("-o" "$last_msg" "-")

  printf '\n== Running %s ==\n' "$role"
  printf 'log: %s\n' "$json_log"
  if ! codex "${args[@]}" < "$prompt_file" > "$json_log" 2>&1; then
    printf '%s role failed. See %s\n' "$role" "$json_log" >&2
    return 1
  fi
  printf '%s last message: %s\n' "$role" "$last_msg"
}

write_executor_prompt() {
  out="$1"
  context_path="$2"
  cat > "$out" <<EOF
You are the Executor in a repo-local autonomous workflow.

Read AGENTS.md and the exact compiled role packet at:
$context_path

Treat that packet as the complete task and authority boundary. Do not discover
an active brief by scanning directories. Change only declared write_paths, run
only declared validation commands plus strictly necessary focused checks, and
do not push. If the packet and repository disagree, stop and report the drift.
EOF
}

write_reviewer_prompt() {
  out="$1"
  context_path="$2"
  cat > "$out" <<EOF
You are the Reviewer / Planner in a repo-local autonomous workflow.

Read AGENTS.md and the exact compiled role packet at:
$context_path

Audit the latest commit and working tree against the packet. This is a
read-only role: do not edit or commit. End with exactly one line containing
CONTINUE, NUDGE, REDIRECT, STOP, or ESCALATE, followed by concise evidence.
EOF
}

if [ "$MODE" != "dry-run" ]; then
  ensure_clean_start
fi

context_dir="$ROOT/outputs/agent-context"
executor_context="$context_dir/current-executor.json"
reviewer_context="$context_dir/current-reviewer.json"
uv run --locked sim2claw check --profile agent --root "$ROOT" >/dev/null
uv run --locked sim2claw agent-context \
  --root "$ROOT" --role executor --output "$executor_context" >/dev/null
uv run --locked sim2claw agent-context \
  --root "$ROOT" --role reviewer --output "$reviewer_context" >/dev/null

if ! uv run --locked python -c \
  'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1]))["execution_admitted"] else 1)' \
  "$executor_context"; then
  printf 'No Executor turn is admitted by %s; stopping cleanly.\n' "$executor_context"
  exit 0
fi

cycle=1
while [ "$cycle" -le "$MAX_CYCLES" ]; do
  printf '\n== Pair cycle %s/%s ==\n' "$cycle" "$MAX_CYCLES"

  if has_stop_sentinel; then
    printf 'Stop sentinel present in GOAL.md. No Executor turn will run.\n'
    exit 0
  fi

  prompt_dir="$(mktemp -d -t autonomous-workflow-prompts-XXXXXX)"
  executor_prompt="$prompt_dir/executor.md"
  reviewer_prompt="$prompt_dir/reviewer.md"
  write_executor_prompt "$executor_prompt" "$executor_context"
  write_reviewer_prompt "$reviewer_prompt" "$reviewer_context"

  run_role "executor" "$executor_prompt"
  uv run --locked sim2claw check --profile agent --root "$ROOT" >/dev/null
  uv run --locked sim2claw agent-context \
    --root "$ROOT" --role reviewer --output "$reviewer_context" >/dev/null
  run_role "reviewer" "$reviewer_prompt"

  rm -rf "$prompt_dir"

  if [ "$MODE" != "loop" ]; then
    break
  fi

  decision="$(latest_reviewer_decision || true)"
  printf 'latest reviewer decision: %s\n' "${decision:-none}"
  if [ "$decision" != "CONTINUE" ]; then
    printf 'Loop stopping because decision is not CONTINUE.\n'
    break
  fi

  if has_stop_sentinel; then
    printf 'Loop stopping because stop sentinel is present.\n'
    break
  fi

  cycle=$((cycle + 1))
  if [ "$cycle" -le "$MAX_CYCLES" ]; then
    sleep "$INTERVAL"
  fi
done

printf '\nPair cycle runner finished.\n'
