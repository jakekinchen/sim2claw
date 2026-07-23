# Goal loop: autonomous development operations and advancement

Status: `ACTIVE_AFTER_GOAL_CREATION`

## Mission

Implement the complete operations and development program defined in
`docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md`. Make the
repository's autonomous-development loop deterministic, resumable,
receipt-gated, process-safe, measurable, and merge-ready; reduce the named
SAIL live-operator maintenance debt; and add a trusted deterministic adapter
boundary. Continue until every milestone D0-D6 is verified or a genuine
external authority blocker is documented.

## Source of truth

Use this order when sources disagree:

1. Current user direction and governing `AGENTS.md` instructions.
2. `docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md`.
3. This goal-loop prompt.
4. `docs/autonomous-workflow/project_state.json`.
5. `GOAL.md`.
6. `.factory/orchestration-ledger.md` as rendered/history evidence only.
7. Pushed commits, receipts, tests, reviewer messages, and run logs.
8. Chat and thread state.

Do not let a stale ledger, chat completion claim, or passing test alone
override the canonical machine state and independent review gates.

## Required outcome

Deliver all of the following on `main`, preserving its completed fast-forward
through `1ee6b7d`:

- reconciled final-review authority with no stale active worker or rereview;
- canonical versioned development-loop state plus deterministic ledger render;
- authority-drift validation across goal/state/ledger/HEAD/remote;
- scoped task/review/test/process leases and receipts;
- exact-identity test reuse and prevention/cleanup of duplicate or orphaned
  local work;
- deterministic merge-readiness packet generation;
- seeded three-mode DevLoopBench with limited, truthful proof claims;
- isolated cleanup of generated campaign state;
- behavior-preserving modularization of SAIL live contracts, decision, state,
  receipts, and adapter boundaries;
- removal or privatization of the disabled simulator-receipt API parameter;
- fixture-backed trusted deterministic adapter evidence with generic admission
  still fail closed when no trusted adapter exists;
- focused, workflow, SAIL CI-tier, and final full-suite evidence;
- fresh independent read-only review, clean branch, and pushed remote equality.

## Milestone order

Only one milestone may be `in_progress`:

1. `D0` plan, goal activation, and authority reconciliation.
2. `D1` canonical state and drift checker.
3. `D2` contracts, leases, receipts, reuse, and lifecycle.
4. `D3` DevLoopBench.
5. `D4` SAIL maintenance hardening.
6. `D5` trusted deterministic adapter boundary.
7. `D6` verification, independent review, and closeout.

Use the invariant outcome and acceptance gate for each milestone in the plan;
do not replace them with an activity checklist or mark them complete from an
agent's own assertion.

## Execution rhythm

For every slice:

1. Inspect `git status`, HEAD/remote, active machine state, plan, goal, latest
   brief/session/reviewer/manager records, and relevant tests.
2. Choose the smallest slice that advances the current milestone.
3. Freeze its allowed paths, proof target, attempts, runtime, and stop rules.
4. Add or update deterministic tests first when practical.
5. Implement with one writer in the checkout.
6. Run the narrowest useful checks and record exact evidence.
7. Update `project_state.json`; render/validate other authority surfaces.
8. Commit and push only reviewed scoped work at a verified boundary.
9. Obtain independent review for milestone transitions and all final proof.
10. Continue without asking the owner unless an explicit authority boundary or
    materially different product choice is reached.

The Manager intervenes only for stale authority, false/repeated blockers,
scope drift, process/resource health, external authority, or final closeout.

## Acceptance criteria

Completion requires every condition below:

1. D0-D6 are marked complete in canonical state with receipt/evidence paths.
2. `GOAL.md`, canonical state, rendered ledger, branch, and remote agree.
3. No worker/process lease remains active; expired owned processes are cleaned
   and unverified PIDs were never signaled.
4. Test reuse is accepted only for exact commit/runtime identity; a final
   unchanged identity has one full-suite receipt.
5. DevLoopBench runs all three modes on identical fixtures and independently
   receipt-gated mode contains every seeded proof/authority defect.
6. Live-operator public behavior and proof boundaries remain compatible or an
   explicit versioned migration receipt explains every intentional change.
7. Generic simulator evidence stays disabled without a trusted adapter; the
   fixture adapter recomputes rather than trusts its consequence.
8. Focused workflow/SAIL tests, automatic SAIL CI tiers, and the full repository
   suite pass at final HEAD.
9. A fresh read-only reviewer reports no blocking correctness finding.
10. Local `main` is clean and pushed equal to `origin/main`.
11. Training, provider, paid compute, simulator promotion, physical capture,
    camera/serial access, robot gateway, and motion authority remain false.

## Evidence standard

Before claiming completion, publish:

- exact changed files and commits;
- plan, goal, config, schema, fixture, report, and receipt hashes;
- exact test commands, counts, durations, and reusable identity;
- workflow state/ledger consistency report;
- task/review/test/process/merge-readiness receipts;
- DevLoopBench scorecard and proof-class statement;
- adapter result and independent evaluator binding;
- final reviewer disposition;
- branch/remote comparison and clean status;
- known limitations, deferred work, owner decisions, and safe claim.

Generated outputs remain ignored. Never commit credentials, datasets, caches,
checkpoints, local process logs, or device observations.

## Decision status

Confirmed:

- Implement all operations and development recommendations from the audit.
- Plan in a repository document before activating this loop.
- Keep one writer and independent review roles.
- The reviewed continuation history is already fast-forwarded into `main`.
- Commit and push verified scoped work directly to `origin/main`.
- Do not revert the fast-forward, rewrite history, or fork completed work.
- The read-only hardware preflight found neither expected SO-101 motor bus,
  neither calibration file, no usable camera/USB device, and no synchronized
  jaw-force or rubber-deformation sensor. Physical capture and motion remain
  blocked by readiness; `/dev/cu.usbmodemSN234567892` is an ignored billboard.

Recommended defaults adopted:

- `project_state.json` is canonical current state.
- The ledger is rendered/history evidence.
- Test proof is content-addressed and reused only on exact identity.
- DevLoopBench is deterministic and offline.
- The first trusted adapter is fixture-backed and grants no campaign authority.

Already exercised owner authority:

- Fast-forward the reviewed SAIL integration to `main`.
- Commit and push verified scoped D0-D6 work to `origin/main`.

Open owner gates:

- Release/publication beyond the authorized repository push.
- Any future provider, spend, simulator campaign, training, physical capture,
  gateway, or motion activity.

## Stop and escalation conditions

Stop and document the exact blocker when:

- unrelated user work would be overwritten;
- the required branch or remote diverges unexpectedly;
- exact evidence identity cannot be verified;
- a public mutation beyond the authorized `origin/main` push, release,
  credential, spend, training, physical, or motion action is required;
- behavior-preserving extraction would invalidate frozen proof without an
  approved versioned migration;
- the same blocker recurs after three evidenced attempts; or
- the final independent review identifies a blocker that cannot be repaired in
  this bounded program.

Do not stop for ordinary implementation difficulty, a recoverable local tool
failure, or a nonblocking reviewer note.

## Progress ledger format

Maintain the live values only in `project_state.json`:

```text
Current state:
Current milestone:
Completed:
Evidence:
Remaining:
Blockers:
Owner gates:
Next step:
```

Render or quote those values into human-readable surfaces; fail validation
instead of silently tolerating drift.
