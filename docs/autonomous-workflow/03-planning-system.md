# Planning System

## Planning Principle

Plans must be file-backed, phase-aware, and easy to audit. The Reviewer should never ask the Executor to infer the next task from chat memory.

## Planning Inputs

Read in this order:

1. Latest user instruction.
2. `GOAL.md` once created.
3. Product/spec docs for this repo.
4. This workflow pack.
5. Latest `docs/session-logs/` entry.
6. Latest `docs/reviewer-messages/` entry.
7. Current git state.

If any of these disagree, the Reviewer must resolve the contradiction before another Executor turn.

## Active Mission File

`GOAL.md` should be short:

```markdown
# GOAL

<optional stop sentinel>

## Active Mission

<one paragraph>

## Current Milestone

M<N> - <name>

## Current Slice

<brief path or next action>

## Stop Conditions

- <condition>

## Human Constraints

- <approval boundary>
```

## Slice Briefs

Briefs live in `docs/briefs/NNN-<topic>.md`.

Each brief should include:

- Feature or task.
- Why this slice exists now.
- Acceptance criteria.
- Files expected to touch.
- Tests or fixtures expected.
- Validation commands.
- Evidence the Executor must produce.
- Reachability or user-facing proof.
- Cross-doc/spec impact.
- Risks and out-of-scope items.

The brief is not a giant plan. It is one slice.

## Hot Routing Matrix

After every Executor slice, the Reviewer routes discoveries immediately. Do not wait until a future retrospective.

| Category | Destination | Owner |
|---|---|---|
| Completed work | Milestone evidence or current state doc | Reviewer |
| Convention / lesson | `docs/session-logs/` and later a lessons file if repeated | Reviewer |
| Product spec correction | Relevant product/spec doc | Reviewer |
| Architecture/data contract change | Relevant architecture/spec doc | Reviewer |
| Next-brief working set | Next `docs/briefs/NNN-*.md` | Reviewer |
| Future in-scope work | Current milestone notes or next slice brief | Reviewer |
| Out-of-scope deferment | Manager escalation | Manager |
| Real blocker | Reviewer decision log, then Manager if human input needed | Reviewer / Manager |
| False blocker suspected | Manager challenge note | Manager |
| Prompt/process improvement | `docs/manager-log/` or workflow doc update | Manager |

## Planning Quality Bar

A next slice is ready only when:

- It has one clear objective.
- It can be validated without guessing.
- The expected files are plausible.
- It does not smuggle in a second unrelated feature.
- It names what evidence would prove success.
- It preserves the project's product thesis.

## Evidence Anchors For Review Decisions

Reviewer and Manager findings use discrete evidence anchors, not continuous confidence percentages.

| Anchor | Route | Meaning |
|---|---|---|
| `0` | Drop | Contradicted by repo evidence, pre-existing, or outside the active scope. |
| `25` | Watch only | Plausible but not verified; do not change the brief or stop the loop. |
| `50` | FYI | Real enough to record as an observation, but no immediate route change. |
| `75` | Actionable | Evidence shows this will affect the current milestone or next slice. Can justify `NUDGE`, `REDIRECT`, or a brief change. |
| `100` | Proven / blocking | Directly confirmed by a command, test, spec conflict, or safety boundary. Can justify `STOP`, `ESCALATE`, or a safe doc correction. |

Rules:

- Every `NUDGE`, `REDIRECT`, `STOP`, and `ESCALATE` should name the anchor and the evidence.
- A finding below `50` should not appear in the main Reviewer decision unless it explains why something was deliberately ignored.
- Corroboration from independent evidence can promote a finding by one anchor step, but not past what the evidence can actually prove.
- Do not invent decimal precision. `75` is enough.

## False Blocker Review

Before escalating "blocked", the Reviewer asks:

- Is the missing information already in a spec or session log?
- Can the repo answer this with search, tests, or a tiny fixture?
- Is this actually a scope decision, not an engineering blocker?
- Can a smaller slice bypass the obstacle while preserving direction?
- Is the prompt stale or overconstrained?

If the answer suggests the blocker is not real, route it to the Manager as a Guardian intervention instead of stopping the loop. The blocker needs anchor `75` or `100` before it can stop execution, unless it is a user-owned approval boundary.
