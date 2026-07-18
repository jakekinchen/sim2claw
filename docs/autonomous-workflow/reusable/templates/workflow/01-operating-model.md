# Operating Model

## Thesis

The workflow is designed for long-running, evidence-backed development in a repo where future Codex sessions need to resume without hidden chat context.

It uses three roles:

- **Executor** - builds one small verified slice.
- **Reviewer / Planner** - audits the slice, updates the plan, and writes the next brief.
- **Manager / Guardian** - keeps the loop aligned with the user's objective and challenges false blockers.

## Source Of Truth

Repo files outrank chat memory. The core surfaces are:

1. Latest user instruction.
2. `GOAL.md`.
3. Product/spec docs for this repo.
4. `docs/autonomous-workflow/`.
5. Latest brief, session log, reviewer message, and manager log.
6. Current git state.

If sources disagree, resolve the contradiction before starting another Executor slice.

## Unit Of Work

The unit of work is a reviewable slice. A slice should usually produce:

- a focused implementation change;
- deterministic tests or equivalent proof;
- a session log;
- a scoped commit;
- a Reviewer decision.

## Milestones

Milestones are invariant outcomes, not a subtask backlog. They should be stable even if the implementation route changes.

## Stop Sentinel

Put this near the top of `GOAL.md` to stop Executor turns:

```text
<stop-orchestrator/>
```

Reviewer and Manager may still run while the sentinel is present to close out, redirect, or ask the user for a decision.
