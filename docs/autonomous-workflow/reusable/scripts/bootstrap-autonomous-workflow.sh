#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE_DIR="$SKILL_DIR/templates"
PROJECT_NAME="$(basename "$ROOT")"

cd "$ROOT"

mkdir -p \
  docs/autonomous-workflow/reusable/scripts \
  docs/autonomous-workflow/reusable/templates \
  docs/autonomous-workflow/reusable/templates/workflow \
  docs/briefs \
  docs/session-logs \
  docs/reviewer-messages \
  docs/manager-log \
  scripts

render_template() {
  src="$1"
  dest="$2"
  if [ -f "$dest" ]; then
    printf 'skip %s (exists)\n' "$dest"
    return
  fi
  sed \
    -e "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" \
    "$src" > "$dest"
  printf 'wrote %s\n' "$dest"
}

copy_if_missing() {
  src="$1"
  dest="$2"
  if [ -f "$dest" ]; then
    printf 'skip %s (exists)\n' "$dest"
  else
    cp "$src" "$dest"
    printf 'wrote %s\n' "$dest"
  fi
}

for dir in docs/briefs docs/session-logs docs/reviewer-messages docs/manager-log; do
  [ -f "$dir/.gitkeep" ] || : > "$dir/.gitkeep"
done

for file in "$TEMPLATE_DIR"/workflow/*.md; do
  base="$(basename "$file")"
  render_template "$file" "docs/autonomous-workflow/$base"
  copy_if_missing "$file" "docs/autonomous-workflow/reusable/templates/workflow/$base"
done

render_template "$TEMPLATE_DIR/milestones.md" "docs/autonomous-workflow/09-autonomous-milestones.md"
render_template "$TEMPLATE_DIR/GOAL.md" "GOAL.md"
render_template "$TEMPLATE_DIR/executor-reviewer-pair-programming.md" "executor-reviewer-pair-programming.md"

for file in "$TEMPLATE_DIR"/*.md; do
  base="$(basename "$file")"
  case "$base" in
    executor-reviewer-pair-programming.md)
      continue
      ;;
  esac
  copy_if_missing "$file" "docs/autonomous-workflow/reusable/templates/$base"
done

for file in "$SCRIPT_DIR"/*.sh; do
  base="$(basename "$file")"
  copy_if_missing "$file" "docs/autonomous-workflow/reusable/scripts/$base"
  chmod +x "docs/autonomous-workflow/reusable/scripts/$base"
done

if [ ! -f scripts/audit_autonomous_workflow.sh ]; then
  cat > scripts/audit_autonomous_workflow.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/../docs/autonomous-workflow/reusable/scripts/audit-autonomous-workflow.sh" "${1:-$PWD}"
EOF
  chmod +x scripts/audit_autonomous_workflow.sh
  printf 'wrote scripts/audit_autonomous_workflow.sh\n'
else
  printf 'skip scripts/audit_autonomous_workflow.sh (exists)\n'
fi

if [ ! -f scripts/bootstrap_autonomous_workflow.sh ]; then
  cat > scripts/bootstrap_autonomous_workflow.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec "$(dirname "$0")/../docs/autonomous-workflow/reusable/scripts/bootstrap-autonomous-workflow.sh" "${1:-$PWD}"
EOF
  chmod +x scripts/bootstrap_autonomous_workflow.sh
  printf 'wrote scripts/bootstrap_autonomous_workflow.sh\n'
else
  printf 'skip scripts/bootstrap_autonomous_workflow.sh (exists)\n'
fi

if [ ! -f scripts/new_workflow_doc.sh ]; then
  cat > scripts/new_workflow_doc.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec docs/autonomous-workflow/reusable/scripts/new-workflow-doc.sh "$@"
EOF
  chmod +x scripts/new_workflow_doc.sh
  printf 'wrote scripts/new_workflow_doc.sh\n'
else
  printf 'skip scripts/new_workflow_doc.sh (exists)\n'
fi

if [ ! -f scripts/run_codex_pair_cycle.sh ]; then
  cat > scripts/run_codex_pair_cycle.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec docs/autonomous-workflow/reusable/scripts/run-codex-pair-cycle.sh "$@"
EOF
  chmod +x scripts/run_codex_pair_cycle.sh
  printf 'wrote scripts/run_codex_pair_cycle.sh\n'
else
  printf 'skip scripts/run_codex_pair_cycle.sh (exists)\n'
fi

if [ ! -f scripts/start_codex_goal_loop.sh ]; then
  cat > scripts/start_codex_goal_loop.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec docs/autonomous-workflow/reusable/scripts/start-codex-goal-loop.sh "$@"
EOF
  chmod +x scripts/start_codex_goal_loop.sh
  printf 'wrote scripts/start_codex_goal_loop.sh\n'
else
  printf 'skip scripts/start_codex_goal_loop.sh (exists)\n'
fi

if [ ! -f scripts/stop_codex_goal_loop.sh ]; then
  cat > scripts/stop_codex_goal_loop.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
exec docs/autonomous-workflow/reusable/scripts/stop-codex-goal-loop.sh "$@"
EOF
  chmod +x scripts/stop_codex_goal_loop.sh
  printf 'wrote scripts/stop_codex_goal_loop.sh\n'
else
  printf 'skip scripts/stop_codex_goal_loop.sh (exists)\n'
fi

printf '\nAutonomous workflow installed for %s.\n' "$PROJECT_NAME"
printf 'Next steps:\n'
printf '1. Research the repo and fill docs/autonomous-workflow/09-autonomous-milestones.md.\n'
printf '2. Fill GOAL.md with the active mission and current milestone.\n'
printf '3. Create the first brief: scripts/new_workflow_doc.sh brief <slug>\n'
printf '4. Audit state: scripts/audit_autonomous_workflow.sh\n'
printf '5. Dry-run a pair cycle: scripts/run_codex_pair_cycle.sh --dry-run\n'
