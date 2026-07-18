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
  --approval <policy>   Codex approval policy. Default: never.
  --allow-dirty         Allow starting from a dirty worktree.
  --dangerous           Use --dangerously-bypass-approvals-and-sandbox.
  -h, --help            Show this help.

The loop continues only when the Reviewer writes a latest decision of CONTINUE.
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
APPROVAL="never"
ALLOW_DIRTY=0
DANGEROUS=0

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
    --approval)
      APPROVAL="${2:?--approval requires a value}"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --dangerous)
      DANGEROUS=1
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

if [ ! -f executor-reviewer-pair-programming.md ]; then
  printf 'executor-reviewer-pair-programming.md missing. Run bootstrap before starting the loop.\n' >&2
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

latest_file() {
  dir="$1"
  if [ -d "$dir" ]; then
    find "$dir" -maxdepth 1 -type f ! -name '.gitkeep' -print | sort | tail -1
  fi
}

latest_reviewer_decision() {
  file="$(latest_file docs/reviewer-messages || true)"
  if [ -z "${file:-}" ]; then
    return 1
  fi
  sed -n '/^## Decision/,/^## /p' "$file" |
    grep -E '^[[:space:]]*`(CONTINUE|NUDGE|REDIRECT|STOP|ESCALATE)`[[:space:]]*$' |
    head -1 |
    tr -d '`[:space:]'
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
  printf '%s\n' "exec"
  printf '%s\n' "--json"
  printf '%s\n' "-C"
  printf '%s\n' "$ROOT"
  if [ -n "$MODEL" ]; then
    printf '%s\n' "-m"
    printf '%s\n' "$MODEL"
  fi
  if [ "$DANGEROUS" -eq 1 ]; then
    printf '%s\n' "--dangerously-bypass-approvals-and-sandbox"
  else
    printf '%s\n' "-s"
    printf '%s\n' "$SANDBOX"
    printf '%s\n' "-a"
    printf '%s\n' "$APPROVAL"
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

  mapfile -t args < <(codex_base_args)
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
  cat > "$out" <<'EOF'
You are the Executor in a repo-local autonomous workflow.

Read and follow:
- executor-reviewer-pair-programming.md
- GOAL.md
- docs/autonomous-workflow/
- latest docs/briefs/NNN-*.md

Your job:
1. If GOAL.md contains <stop-orchestrator/>, do not implement. Report that execution is stopped.
2. Otherwise implement exactly one smallest useful slice from the active brief.
3. Run focused and broad validation appropriate to the slice.
4. Prove reachability from a real product path.
5. Write docs/session-logs/NNN-executor-*.md with files changed, validation, reachability, evidence, flags for Reviewer, and next suggested slice.
6. Commit only scoped files with explicit git add paths. Do not push.

If blocked, write a session log explaining the blocker category, evidence, and smallest next action. Do not wait for user input inside this unattended turn.
EOF
}

write_reviewer_prompt() {
  out="$1"
  cat > "$out" <<'EOF'
You are the Reviewer / Planner in a repo-local autonomous workflow.

Read and follow:
- executor-reviewer-pair-programming.md
- GOAL.md
- docs/autonomous-workflow/
- latest docs/briefs/NNN-*.md
- latest docs/session-logs/NNN-executor-*.md
- latest commit and git diff/status

Your job:
1. Audit the Executor's latest slice from repo evidence.
2. Choose exactly one decision: CONTINUE, NUDGE, REDIRECT, STOP, or ESCALATE.
3. Include an evidence anchor for any NUDGE, REDIRECT, STOP, or ESCALATE.
4. Write docs/reviewer-messages/NNN-*.md.
5. If the decision is CONTINUE, write the next docs/briefs/NNN-*.md and update GOAL.md Current Slice if needed.
6. If the decision is STOP, add <stop-orchestrator/> near the top of GOAL.md.
7. Commit only scoped reviewer/planning docs with an appropriate docs: commit. Do not push.

Do not write product code. If a human decision is required, choose ESCALATE and make the reason concrete.
EOF
}

if [ "$MODE" != "dry-run" ]; then
  ensure_clean_start
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
  write_executor_prompt "$executor_prompt"
  write_reviewer_prompt "$reviewer_prompt"

  run_role "executor" "$executor_prompt"
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
