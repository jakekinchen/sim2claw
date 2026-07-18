# Executor / Reviewer / Manager Pair Programming Session

`sim2claw` uses a supervised Codex pair as the base workflow:

- **Executor** implements one smallest useful, reviewable slice from the active brief.
- **Reviewer / Planner** audits the Executor's latest slice, keeps the plan coherent, and decides whether to continue, nudge, redirect, stop, or escalate.
- **Manager / Guardian** is the user's durable interface and the meta-controller that challenges false blockers, watches context/process health, and improves prompts or workflow docs when repeated friction appears.

The full workflow lives in [docs/autonomous-workflow](./docs/autonomous-workflow/README.md).

## Core Rule

Repo evidence beats chat memory.

Every autonomous turn should leave enough durable state for a fresh Codex session to reconstruct:

- the active mission;
- the slice attempted;
- files changed;
- validation run;
- reviewer decision;
- any manager intervention;
- next recommended slice.

## Normal Flow

1. Manager confirms the mission and human constraints.
2. Reviewer writes or refreshes `docs/briefs/NNN-*.md`.
3. Executor reads the brief, implements one slice, validates it, writes `docs/session-logs/NNN-executor-*.md`, and commits scoped files.
4. Reviewer audits the commit and log, then writes `docs/reviewer-messages/NNN-*.md`.
5. Manager intervenes only for escalation, context risk, stale planning, false blockers, or process optimization.

## Reviewer Decisions

The Reviewer chooses exactly one:

| Decision | Meaning |
|---|---|
| `CONTINUE` | Slice is valid and the next slice is clear. |
| `NUDGE` | Executor needs a tactical correction. |
| `REDIRECT` | The mission, brief, or docs are stale and need durable repair. |
| `STOP` | Mission complete, unsafe to continue, or waiting on a human. |
| `ESCALATE` | Manager or human input is required. |

`NUDGE`, `REDIRECT`, `STOP`, and `ESCALATE` decisions should include an evidence anchor from `0 / 25 / 50 / 75 / 100`.

## Stop Sentinel

When autonomous execution should stop, put this near the top of `GOAL.md`:

```text
<stop-orchestrator/>
```

The Executor must not start a new product slice while the sentinel is present. Reviewer and Manager may still run to close out, redirect, or ask the user for a decision.

## Current Workflow Helpers

```bash
scripts/audit_autonomous_workflow.sh
scripts/bootstrap_autonomous_workflow.sh
scripts/new_workflow_doc.sh brief <slug>
scripts/new_workflow_doc.sh executor-log <slug>
scripts/new_workflow_doc.sh reviewer-message <slug>
scripts/new_workflow_doc.sh manager-log <slug>
scripts/run_codex_pair_cycle.sh --dry-run
scripts/run_codex_pair_cycle.sh --once
scripts/start_codex_goal_loop.sh --max-cycles 10
scripts/stop_codex_goal_loop.sh
```

Use `audit_autonomous_workflow.sh` before starting, after interruptions, and before claiming a milestone.
