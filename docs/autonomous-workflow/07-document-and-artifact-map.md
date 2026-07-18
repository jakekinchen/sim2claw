# Document and Artifact Map

## Current Docs

| Path | Owns |
|---|---|
| `GOAL.md` | Active mission, current slice, stop sentinel, human constraints. |
| `executor-reviewer-pair-programming.md` | Root quickstart and role overview for the pair. |
| `docs/autonomous-workflow/` | Autonomous workflow strategy and protocols. |
| `docs/autonomous-workflow/09-autonomous-milestones.md` | Invariant milestone gates. |
| `configs/data/physical_teleop_episode_intake_20260718.json` | Machine-readable pointers, hashes, review, and lane routing for the owner-local physical source cohort. |
| `docs/run-logs/2026-07-18-physical-episode-intake.md` | Human-readable physical episode assessment and admission boundary. |
| `configs/evaluations/pawn_rank12_bidirectional_v1.json` | Frozen A1↔A2 through H1↔H2 product benchmark, resets, seeds, gates, and scorecard. |
| `docs/decisions/0006-pawn-rank12-bidirectional-evaluation.md` | Owner decision and ACT/GR00T/Brev execution boundary for the final benchmark. |

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
| Physical source episode inventory | Versioned `configs/data/physical_teleop_episode_intake_*.json` ledger; raw artifacts remain under ignored `datasets/act_source_recordings/` |
| Final product evaluation | `configs/evaluations/pawn_rank12_bidirectional_v1.json`; exact rows remain zero-training-row held-outs |

If a new doc duplicates one of these concerns, delete or merge it before it drifts.
