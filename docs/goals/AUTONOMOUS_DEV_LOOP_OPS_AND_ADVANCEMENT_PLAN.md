# Autonomous Development Loop Operations and Advancement Plan

Status: `READY_FOR_GOAL_LOOP_EXECUTION`

Date: 2026-07-22

## Mission

Turn the repository's useful but partly manual autonomous-development workflow
into a deterministic, resumable, and measurable control plane. Preserve the
current Executor / Reviewer / Manager separation while making project state,
task leases, test evidence, review packets, process cleanup, and completion
claims mechanically verifiable. Then reduce the highest-risk maintenance debt
in the SAIL live operator and add a trusted deterministic evaluator-adapter
boundary without opening simulator experiments, training, physical capture, or
robot motion.

## Source of truth

Use this order when sources disagree:

1. Current user direction and repository `AGENTS.md` instructions.
2. This plan.
3. The active goal-loop prompt created from this plan.
4. `docs/autonomous-workflow/project_state.json` as canonical machine state.
5. `GOAL.md` as the current human mission and stop boundary.
6. `.factory/orchestration-ledger.md` as an append-only rendered operational
   history, never as a competing current-state authority.
7. Pushed commits, receipts, test reports, reviewer messages, and run logs.
8. Chat or thread summaries, which are execution context only.

## Current verified baseline

- The reviewed SAIL continuation was fast-forwarded after owner authorization.
  Local `main` and `origin/main` are equal at
  `1ee6b7d5f45aecb3fc95006b6abf1141713cb927`; D0-D6 execute directly on
  `main` with scoped commit/push authority.
- The final independent correctness review found no blocking issue and ran six
  focused checks successfully.
- The uninterrupted repository suite recorded 859 passed, 3 skipped, and 328
  subtests.
- `project_state.json`, `GOAL.md`, and the orchestration ledger have not all
  been reconciled to that final review. The ledger still contains active and
  pending entries from commit `5bc796f`.
- The workflow runner prevents two pair cycles through a directory lock, but
  it does not yet issue durable task/process leases, cache test proof by exact
  code/environment identity, or close orphaned subprocesses mechanically.
- `src/sim2claw/sail/live_operator.py` combines contracts, decisions, state
  binding, execution assembly, output publication, and receipt verification in
  1,843 lines. `tests/test_sail_live_operator.py` combines the corresponding
  behaviors in 1,116 lines.
- Generic simulator evidence admission is intentionally disabled. A future
  adapter must recompute concrete mutations and consequences; it may never
  accept an agent-authored result merely because its hashes are internally
  consistent.

## Intended outcome

The finished repository has one deterministic development-loop control plane
that can:

1. create a scoped task contract and lease;
2. admit one writer and independent reviewers without shared-writer races;
3. bind review and test evidence to an exact commit and runtime identity;
4. reuse unchanged full-suite proof instead of launching duplicate work;
5. detect and clean up expired or orphaned local processes;
6. reject authority drift across machine state, goal, ledger, branch, and
   remote commit;
7. generate a merge-readiness packet with truthful remaining owner gates;
8. measure the control-plane value through a deterministic DevLoopBench;
9. keep SAIL evidence admission modular and fail closed behind deterministic
   adapters; and
10. preserve all training, provider, simulator-promotion, physical-capture,
    and motion boundaries as false.

## Non-goals and authority boundaries

- Do not resume B2-02X or open another C2 family.
- Do not run training, provider campaigns, paid compute, camera/serial access,
  physical capture, robot gateway calls, or motion.
- Do not revert, duplicate, or fork the completed fast-forward into `main`.
  Scoped verified D0-D6 commits may be pushed directly to `origin/main` under
  the owner's explicit authorization.
- Do not add more agent roles. Use one Executor writer, an independent
  Reviewer, and a thin Manager / Guardian.
- Do not claim that deterministic DevLoopBench fixtures measure general model
  intelligence. They measure control-plane defect containment, proof quality,
  duplicate-work prevention, and recovery behavior.
- Do not enable generic simulator result admission until a concrete adapter
  independently recomputes the declared mutation and consequence.

The read-only physical readiness preflight found no usable acquisition path:

- LeRobot 0.6.0 is installed;
- expected leader suffix `0448141` and follower suffix `0406411` are absent;
- both leader and follower calibration JSON files are absent;
- `/dev/cu.usbmodemSN234567892` is the ignored billboard, not a motor bus;
- no usable camera/USB device was enumerated; and
- no synchronized jaw-force or rubber-deformation/profile sensor is present.

Physical capture and robot motion therefore remain closed by hardware and
calibration readiness even though repository commit/push authority is open.
Do not open the physical gateway or manufacture measurement evidence.

## Target architecture

### Canonical workflow state

Extend `docs/autonomous-workflow/project_state.json` with a versioned
`autonomous_dev_loop` section containing:

- active goal and plan identities;
- branch, base commit, current commit, and expected remote;
- state-machine phase and terminal state;
- worker/reviewer leases and allowed paths/actions;
- exact test receipts and reuse decisions;
- process cleanup results;
- review findings and merge-readiness;
- owner gates and proof boundaries;
- aggregate effectiveness metrics.

Add a deterministic compiler/checker that validates this state and renders the
current ledger summary. Existing historical ledger sections remain preserved.

### Development state machine

Use these states:

`INSPECT -> CONTRACT -> IMPLEMENT -> FOCUSED_VERIFY -> INDEPENDENT_REVIEW ->`
`REPAIR -> FULL_VERIFY -> FINAL_REVIEW -> MERGE_READY -> CLOSED`

`BLOCKED`, `STOPPED`, and `FAILED` are explicit terminal or resumable states.
Every transition has required inputs, allowed outputs, a receipt, and a stop
condition. An LLM proposes work but cannot set its own review result, reuse a
receipt with the wrong identity, widen authority, or promote itself.

### Task and process leases

Each lease binds:

- task/role identity;
- repository and branch;
- base/current commit;
- allowed paths and operations;
- wall-time and attempt ceilings;
- process ID/start token when a process exists;
- heartbeat and expiry;
- teardown policy;
- status and receipt digest.

Expired local process leases are cleaned only after verifying PID identity and
repository ownership. Never signal an unverified process.

### Test evidence and reuse

Test receipts bind:

- commit tree and relevant diff identity;
- `uv.lock`, `pyproject.toml`, Python, platform, and dependency identity;
- exact command and selected test nodes;
- exit code, duration, counts, and log hash;
- tier and proof boundary.

Only an exact identity match permits reuse. One full suite per unchanged
identity is the default. Reviewers run focused checks for their findings and
reuse the full-suite receipt unless code or runtime identity changed.

### Merge-readiness packet

Generate one read-only packet that records:

- scoped commits and changed paths;
- focused, tiered, and full-suite receipts;
- independent review decisions and resolved findings;
- authority consistency result;
- branch/remote synchronization;
- unresolved owner decisions;
- generated-artifact and ignored-output status;
- final safe claim.

The packet confers no merge or release authority.

### DevLoopBench

Create seeded, deterministic cases representing defects observed in this loop:

- a self-asserted completion claim;
- stale authority files;
- mismatched branch or commit identity;
- a replayed test receipt;
- a duplicate process launch;
- an orphaned process lease;
- a reviewer finding requiring repair;
- a widened authority claim;
- a stale receipt after a new state head; and
- a clean merge-ready slice.

Compare three declared modes over identical fixtures:

1. `single_worker`;
2. `worker_self_review`;
3. `independent_receipt_gated`.

Report escaped defects, detected defects, false completion, duplicate work,
required repairs, receipt validity, and terminal status. Fixture results prove
the deterministic control mechanics only.

### SAIL modularization and adapter boundary

Refactor by behavior-preserving extraction, keeping the public live-operator
entry points stable until callers migrate:

- `live_contracts.py`: typed contract loading and source bindings;
- `live_decision.py`: residual, belief, acquisition, posterior, invariance,
  consequence, and closure composition;
- `live_state.py`: canonical state keys, locking, transactional append, and
  validation;
- `live_receipts.py`: output bindings and read-time verification;
- `live_adapters.py`: trusted adapter protocol and fail-closed registry;
- `live_operator.py`: small orchestration facade.

Remove or privatize the misleading disabled simulator-receipt parameter.
Provide pytest fixtures that isolate and clean generated campaign state. Add
multiprocess locking, interrupted-write, stale-lease, and resume tests.

The first trusted-adapter implementation is fixture-backed and deterministic:
it receives a frozen intervention plus raw fixture, applies/recomputes the
declared mutation through reviewed code, runs the evaluator locally, and emits
a receipt whose result is derived rather than caller-supplied. It is a
development proof of the adapter boundary, not authorization to run C2 or
promote a simulator.

## Milestones and acceptance gates

### D0 - Plan and goal activation

**Outcome:** This plan and its derived goal-loop prompt are committed to
`main`, and current authority is reconciled to the final review and completed
fast-forward.

**Gate:** Workflow audit passes; plan/prompt hashes and active state are
recorded; no stale active worker or pending rereview remains.

### D1 - Canonical control-plane state and drift check

**Outcome:** One versioned machine state owns current workflow truth; human
surfaces are validated/rendered from it.

**Gate:** Positive and negative tests cover goal/state/ledger/HEAD/remote
agreement, stale commits, contradictory terminal states, and unauthorized
authority widening.

### D2 - Contracts, leases, receipts, and lifecycle

**Outcome:** Task, review, test, and process lifecycle is deterministic and
resumable.

**Gate:** Tests cover one-writer admission, exact test reuse, changed-identity
rerun, verified orphan cleanup, PID mismatch refusal, crash resume, and
terminal closeout.

### D3 - DevLoopBench

**Outcome:** The three declared modes run over the same seeded cases and emit a
deterministic scorecard/receipt.

**Gate:** Independent receipt-gated mode contains every seeded authority and
proof defect; documentation states the benchmark's limited proof class.

### D4 - SAIL maintenance hardening

**Outcome:** Live-operator behavior is split into reviewable modules, the
disabled public parameter is gone/private, and generated state is isolated.

**Gate:** Existing live-operator output/receipt hashes either remain identical
or are explicitly versioned with a migration receipt; all current focused
tests pass; test cleanup leaves no undeclared state.

### D5 - Trusted deterministic adapter boundary

**Outcome:** A fixture-backed adapter independently derives result evidence and
the generic path remains fail closed without a registered trusted adapter.

**Gate:** Tests reject caller-authored results, wrong mutation/evaluator/source
identity, stale receipts, adapter substitution, and authority widening. No C2,
provider, training, or physical lane is opened.

### D6 - Verification, independent review, and closeout

**Outcome:** The whole program is verified, independently reviewed, and pushed
on `main`.

**Gate:** Focused workflow/SAIL suites, automatic SAIL CI tiers, and the full
repository suite pass once at the final identity; a fresh read-only review has
no blocking finding; project state, goal, ledger, local `main`, and
`origin/main` agree. The committed project state remains an active,
nonterminal `FULL_VERIFY` candidate with D6 in progress; it may not claim its
own post-commit receipts. After push, a generated merge-readiness v2 packet is
the operational terminal authority only when it embeds and verifies exactly
the `final_focused`, `sail_fast_contract`, `sail_synthetic_golden`,
`sail_integration`, and `full_repository` receipts, one covering fresh `PASS`
review, a current state digest and HEAD, remote equality, a clean tracked
worktree, and zero live development-loop process leases.

## Implementation slices

Execute the smallest verified slice at a time:

1. Reconcile final review and establish the new plan/goal state.
2. Add schemas/types and canonical workflow-state validation.
3. Add the authority-drift checker and ledger renderer.
4. Add task/review/test receipts and exact-identity reuse.
5. Add process leases, verified cleanup, and crash recovery.
6. Add merge-readiness packet generation.
7. Add DevLoopBench fixtures, evaluator, scorecard, CLI, and receipt.
8. Isolate test-generated campaign state.
9. Extract live contract/decision/state/receipt modules without behavior drift.
10. Add the trusted adapter protocol and deterministic fixture adapter.
11. Run verification, repair findings, independently rereview, reconcile, and
    push.

## Required evidence

Before completion, preserve:

- plan and goal-loop hashes;
- current-state and rendered-ledger receipts;
- task, review, test, process, and merge-readiness schemas/fixtures;
- DevLoopBench config, fixture identities, scorecard, and receipt;
- adapter fixture, evaluator identity, result, and receipt;
- focused and full-suite logs/counts;
- changed-file inventory and commit list;
- independent reviewer disposition;
- branch/remote equality;
- explicit false values for release, training, provider, simulator promotion,
  physical capture, and robot motion authority; repository merge/push authority
  remains the separately recorded owner-approved scope.

Generated runtime data belongs under ignored `outputs/` or `/tmp`; only frozen
fixtures, schemas, compact receipts, and read-only summaries are committed.

## Stop and escalation conditions

Stop or escalate when:

- a required change would overwrite unrelated user work;
- the active branch or remote diverges unexpectedly;
- a public mutation other than the authorized scoped `origin/main` push, a
  release, credential, spend, training, physical capture, or robot operation
  is required;
- exact receipt identity cannot be established;
- the same blocker recurs after three evidenced attempts;
- a behavior-preserving refactor changes frozen proof without an explicit
  versioned migration; or
- verification reveals a regression that cannot be repaired inside the
  bounded program.

## Progress ledger

```text
Current state:
Completed:
Evidence:
Remaining:
Blockers:
Next step:
```

Only `project_state.json` owns the live values. Other documents quote or render
that state and must fail validation when stale.
