# Document and Artifact Map

## Current Docs

| Path | Owns |
|---|---|
| `GOAL.md` | Active mission, current slice, stop sentinel, human constraints. |
| `executor-reviewer-pair-programming.md` | Root quickstart and role overview for the pair. |
| `docs/autonomous-workflow/` | Autonomous workflow strategy and protocols. |
| `docs/autonomous-workflow/09-autonomous-milestones.md` | Invariant milestone gates. |

Add project-specific product and architecture docs to this table after setup.

## Target Workflow Artifacts

| Path | Created When | Owns |
|---|---|---|
| `docs/briefs/NNN-*.md` | Before each implementation slice | Slice objective, acceptance criteria, tests, validation, expected evidence. |
| `docs/session-logs/NNN-executor-*.md` | After each Executor slice | Evidence of what changed and how it was validated. |
| `docs/session-logs/NNN-review-*.md` | After a substantial Reviewer audit | Review evidence and decision rationale. |
| `docs/reviewer-messages/NNN-*.md` | Every Reviewer decision | `CONTINUE`, `NUDGE`, `REDIRECT`, `STOP`, or `ESCALATE`. |
| `docs/manager-log/NNN-*.md` | Manager intervention | False blocker challenges, user escalation, context cycle, process optimization. |

## Single Source Of Truth By Concern

| Concern | Source |
|---|---|
| Product intent | Project-specific product/spec doc |
| Architecture | Project-specific architecture/spec doc |
| Build order | `docs/autonomous-workflow/09-autonomous-milestones.md` plus latest brief |
| Active work | `GOAL.md` plus latest brief |
| Completed evidence | `docs/session-logs/` plus commits |
| Review decisions | `docs/reviewer-messages/` |
| Manager interventions | `docs/manager-log/` |

If a new doc duplicates one of these concerns, delete or merge it before it drifts.
