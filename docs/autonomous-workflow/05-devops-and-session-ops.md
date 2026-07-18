# DevOps and Session Ops

## Operational Principle

The workflow should make the loop observable. A human should be able to ask "what is happening?" and get an answer from repo files, logs, commits, and running processes.

## Startup Audit

Before starting or resuming automation:

```bash
git status --short --branch
git log --oneline -5
find . -maxdepth 3 -type f -print | sort
scripts/audit_autonomous_workflow.sh
```

Add project-specific install, lint, test, and smoke commands as soon as they exist.

## Automation Scripts

The workflow installs these repo-local helpers:

| Script | Purpose |
|---|---|
| `scripts/audit_autonomous_workflow.sh` | Reports branch, dirty state, active mission, latest workflow artifacts, and warnings. |
| `scripts/run_codex_pair_cycle.sh` | Runs exactly one Executor turn then one Reviewer turn, with a lock. |
| `scripts/start_codex_goal_loop.sh` | Starts the supervised loop in the background with a pid file and log. |
| `scripts/stop_codex_goal_loop.sh` | Stops the background loop started by `start_codex_goal_loop.sh`. |
| `scripts/new_workflow_doc.sh` | Creates numbered briefs, session logs, reviewer messages, and manager logs. |

Use `scripts/run_codex_pair_cycle.sh --dry-run` before unattended execution. Use `--once` for a single real pair cycle and `--loop` only when `GOAL.md`, milestones, and the active brief are correct.

Loop continuation rule: background loop mode continues only when the latest Reviewer decision is `CONTINUE`. Any `STOP`, `ESCALATE`, `REDIRECT`, `NUDGE`, missing decision, command failure, or stop sentinel ends the loop.

## Script-First Ops

When the workflow repeatedly performs deterministic processing, move the mechanics into a repo-local script and let the agent interpret the bounded output.

Good script candidates:

- Auditing workflow state.
- Extracting latest session markers.
- Summarizing validation logs.
- Checking milestone gates.
- Normalizing generated artifact paths.
- Detecting stale briefs or stop sentinels.

Rules:

- Scripts own parsing, filtering, counting, and deterministic classification.
- Agents own judgment, routing, and communication.
- Prefer bounded stdout with clear warnings. Add machine-readable output only when another script or agent will consume it.
- Do not make the model re-parse large logs or session transcripts when a small extractor would produce the needed facts.

## Dirty Worktree Rule

The supervised loop should refuse to start from a dirty tree unless the Manager or Reviewer explicitly allows it for a known reason.

Dirty-tree exceptions:

- The user has intentionally staged or edited files.
- The current slice requires generated artifacts.
- The Manager is doing workflow-doc edits.

Any exception must be recorded in the session log.

## Logs and Markers

Durable logs:

- `docs/session-logs/`.
- `docs/reviewer-messages/`.
- `docs/manager-log/`.

Temp logs help monitor a running cycle. Durable logs are what future sessions should trust.

Runtime logs for the background loop live under `/tmp/autonomous-project-workflow/<repo>/`.

## External Services and Spend

Default posture:

- No paid API call without an approved purpose.
- No credential creation without human approval.
- No destructive operation without human approval.

If a model or external service is used, record purpose, inputs, outputs, model/service, and failure behavior in the session log.
