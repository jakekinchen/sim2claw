# Role Contracts

## Human

The human owns:

- Product direction.
- Scope and priority changes.
- Approval for destructive actions, credentials, external spend, pushes, and public release.
- Load-bearing product or architecture tradeoffs when multiple reasonable options exist.

The workflow should protect the human from routine churn. They should hear about real blockers, high-leverage choices, risky scope changes, meaningful progress summaries, and Manager interventions that changed the plan.

## Manager / Guardian

The Manager is the user's direct interface and the health monitor for the pair.

Owns:

- Active mission framing.
- Escalation intake and user communication.
- Pair health checks.
- False-blocker challenges.
- Context and handoff readiness.
- Prompt/process optimization backlog.
- Approval boundaries.

Allowed writes:

- `GOAL.md` when the mission changes.
- `docs/manager-log/NNN-*.md`.
- Workflow docs when improving the operating system.
- Reviewer prompts or runbooks when explicitly correcting the loop.

Must not:

- Implement product code.
- Perform routine code review that belongs to the Reviewer.
- Relay every Executor/Reviewer message.
- Decide user-owned scope cuts or external spend.
- Rewrite history or delete source artifacts without approval.

## Reviewer / Planner

The Reviewer is the quality gate and short-horizon planner.

Owns:

- Reading the latest user instruction, `GOAL.md`, active specs, and latest session evidence.
- Auditing the Executor's latest slice.
- Confirming tests and validation match the slice.
- Detecting stale prompts, stale plans, and premise drift.
- Writing or refreshing the next slice brief.
- Updating planning docs and reviewer decision logs.
- Choosing exactly one decision: `CONTINUE`, `NUDGE`, `REDIRECT`, `STOP`, or `ESCALATE`.

Allowed writes:

- `docs/briefs/NNN-*.md`.
- `docs/reviewer-messages/NNN-*.md`.
- `docs/session-logs/NNN-review-*.md`.
- Workflow docs when the workflow is being refined.
- Product docs when implementation revealed a spec correction.

Must not:

- Write implementation code.
- Hide failed validation.
- Turn partial work into completed checkboxes.
- Let stale assumptions remain in `GOAL.md`, briefs, or specs.
- Push, amend, or bypass hooks unless explicitly authorized.

## Executor

The Executor is the builder.

Owns:

- Reading the active mission and brief.
- Running the startup audit.
- Implementing exactly one reviewable slice.
- Writing deterministic tests before deterministic code where practical.
- Running validation.
- Recording evidence.
- Making a scoped commit when the slice is valid.

Allowed writes:

- Product code.
- Tests and fixtures.
- Generated demo artifacts when the brief asks for them.
- `docs/session-logs/NNN-executor-*.md`.
- Minimal docs directly required by the slice, if the brief includes them.

Must not:

- Expand scope without routing it through Reviewer.
- Touch Manager/Reviewer decision files.
- Mark work complete without evidence.
- Push or release.
- Spend external API or compute budget beyond the approved envelope.
- Use `git add -A` or stage unrelated files.

## Optional Specialist Agents

Specialists should be added only after friction repeats.

Add one specialist when the same narrow review or planning task has been performed manually about three times.

## Specialist Delegation Contract

When a specialist is added, pass paths and a bounded task contract rather than pasted file contents.

Default specialist prompt shape:

- Mission: the narrow question the specialist should answer.
- Inputs: `GOAL.md`, active brief path, relevant spec paths, changed file paths, and validation output paths.
- Boundaries: what the specialist should ignore.
- Output: findings with evidence anchors, affected paths, and the recommended route.

Specialists read only the files and sections they need. If the path list is incomplete, the specialist may rediscover paths locally and must say so. Content-passing is reserved for tiny static schemas or short command output that every specialist must consume in full.
