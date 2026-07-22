# Goal Loop: LLM-Guided Corrective Intervention

## Mission

Build and verify a hardware-free loop in which a language-model agent diagnoses
one training/development counterexample, proposes a small task-space repair, a
deterministic compiler turns that proposal into bounded SO-101 joint targets,
and the existing independent evaluator decides whether the resulting corrective
suffix may enter LF-09. Add posterior-constrained robustness evaluation and an
Inspect benchmark without granting the LLM evaluator, promotion, held-out, or
robot authority.

## Source of truth

Use this order when sources disagree:

1. The latest user instruction and repository `AGENTS.md`.
2. Frozen task, source-episode, split, and evaluator contracts under `configs/`.
3. `GOAL.md` and `docs/autonomous-workflow/project_state.json` for the broader
   project state; do not overwrite unrelated active-lane changes.
4. `docs/decisions/0004-goal-conditioned-act-pick-place.md`.
5. Existing LF-09/LF-12 code and independently replayed evidence.
6. This goal loop, its active brief, task ledger, and run log.
7. Research papers as rationale only; they cannot prove repository capability.

## Intended outcome

The repository exposes one runnable, deterministic fixture that executes this
chain:

```text
training/dev counterexample
  -> transfer-observable failure packet
  -> typed LLM proposal
  -> bounded Cartesian waypoint compiler
  -> exact-state branch and full replay
  -> nominal plus posterior robustness score
  -> independent suffix admission or typed rejection
  -> LF-09 dataset lineage
  -> optional retraining candidate
  -> sealed evaluation outside trainer/agent authority
```

The fixture must prove infrastructure and synthetic/simulation behavior only.
It must not claim physical transfer or B--G policy success.

## Non-goals and authority boundaries

- No physical motion, camera, serial, gateway, credential, or paid compute.
- No held-out failure may be shown to the proposer or converted to training.
- The LLM never emits raw joint targets and never owns a control-rate loop.
- The LLM proposes task-space intent. A declared deterministic geometric
  expert owns the compiled actions and retains the proposal digest as lineage.
- Evaluator-only privileged state may restore and score a branch but may not
  enter the proposer packet or policy adapter.
- Domain randomization does not substitute for exact replay, calibration, or a
  separately measured real-data posterior.
- Inspect records and scores agent attempts; it does not admit data, train,
  promote, or execute hardware.

## Invariant milestones

### L0 - Frozen contracts and benchmark boundary

The proposal, failure packet, compiler, posterior, scoring, budget, split, and
claim schemas are frozen before model-generated rows are admitted.

Gate: contract tests reject unknown keys, non-finite values, raw joint actions,
held-out membership, evaluator-only features, excessive deltas/horizons,
unbounded posteriors, and mutable evaluator identities.

### L1 - Deterministic bounded compiler

One to three target-relative Cartesian waypoints compile into finite float32
20 Hz absolute joint targets through the existing SO-101 damped least-squares
IK path. The compiler rejects IK residuals above 3 mm, joint-limit violation,
rate violation, collision, unsupported reference frames, and silent clipping.

Gate: deterministic unit tests plus at least one real MuJoCo fixture.

### L2 - Exact-state replay and evaluator-owned repair decision

A training/dev counterexample can be branched from the exact recorded
integration state. The original prefix remains counterexample evidence; a full
prefix-plus-suffix replay is independently evaluated; only successful suffix
rows are eligible for LF-09.

Gate: success and adversarial rejection fixtures bind parent, prefix, branch,
proposal, compiler, suffix, scene, and evaluator digests.

### L3 - Posterior-constrained robustness

Accepted nominal repairs are replayed over an immutable, bounded posterior of
identified uncertainty. Results retain per-sample consequences and reject broad
or unsupported randomization. Training/dev and sealed seeds are disjoint.

Gate: deterministic posterior sampling, threshold tests, non-regression tests,
and a receipt separating nominal success from robustness.

### L4 - Dataset and retraining lineage

Admitted suffix rows enter a versioned LF-09 dataset without held-out or failed
prefix rows. Any checkpoint binds the exact dataset, recipe, runtime, and
evaluator identities. Training cannot promote itself.

Gate: byte-bound dataset receipt and one local fixture checkpoint/evaluation,
or an explicit evidence-backed blocker if the existing trainer cannot consume
the correction mixture without changing a frozen contract.

### L5 - Agent-neutral Inspect benchmark

Codex CLI and Claude Code receive the same public failure packets, skills,
tools, budgets, candidate limits, and simulator-call budgets. Deterministic
baselines include unchanged policy, random nudge, bounded search, and oracle
fixture repair. Provider-backed model runs remain separately authorized.

Gate: mock harness runs, deterministic scorer tests, sandbox audit, and no
provider/robot/paid-compute side effects.

### L6 - End-to-end proof and closeout

One command runs the hardware-free fixture from counterexample through final
receipt. Full tests, clean-room build, diff check, run log, proof-class wording,
and remaining limitations are recorded.

Gate: all preceding milestones pass; no open safety or scientific-identity
failure remains. Otherwise the goal stays active or is marked blocked only
under the product's repeated-blocker rule.

## Task ledger

Status values: `pending`, `in_progress`, `complete`, `blocked`.

| ID | Task | Status | Required evidence |
|---|---|---|---|
| T00 | Audit authority, dirty work, existing LF and GapBench surfaces | complete | Scoped audit in the run log |
| T01 | Freeze proposal/failure/posterior/score contracts | complete | Frozen config, validators, and negative tests |
| T02 | Implement transfer-observable failure packet builder | complete | Leakage, route, identity, and digest tests |
| T03 | Implement deterministic Cartesian-to-IK compiler | complete | Unit and real MuJoCo tests |
| T04 | Implement exact branch replay and consequence trace | complete | Exact restoration and branch-only receipt tests |
| T05 | Implement proposal scorer and acceptance policy | complete | Baseline-uplift/non-regression/authority tests |
| T06 | Implement posterior sampler and robustness runner | complete | Deterministic split sampling and receipt tests |
| T07 | Connect accepted suffix to LF-12/LF-09 | complete | Canonical full-episode replay; 561 admitted suffix rows; zero failed-prefix rows |
| T08 | Connect dataset to local retraining/evaluation fixture | complete | Byte-bound correction mixture; two-update CPU ACT checkpoint and independent runtime smoke |
| T09 | Add Inspect repair task, shared skills, tools, and scorers | complete | Four matched cases; six tools; five skills; Codex/Claude mock harness proof |
| T10 | Add random-search/oracle controls and paper metrics | complete | Byte-identical unchanged/random/search/oracle comparison summary |
| T11 | Run full verification and write closeout evidence | complete | 532 tests + 328 subtests; build, lock, compile, diff, Docker cleanup, run log |

## Decision status

Confirmed:

- Current corrective admission already requires exact pre-failure state and an
  independently passing full replay.
- Held-out counterexamples contribute zero training rows.
- Current source execution uses float32 absolute six-joint targets at 20 Hz.
- Inspect GapBench already supplies isolated Codex/Claude harnesses and a
  single-use sealed scoring pattern.

Recommended defaults subject to contract tests:

- At most three Cartesian waypoints per proposal.
- At most 20 compiled 20 Hz actions and one second of intervention horizon.
- At most 10 mm translation per waypoint for the first centering lane.
- Nominal strict success plus at least 12/16 bounded posterior successes, zero
  safety violations, and no regression on frozen already-passing fixtures.
- The first supported lane is pre-contact pawn centering; contact-rich repair
  remains unsupported until the observation and contact model can identify it.

Open until measured rather than guessed:

- Real posterior parameters and ranges for latency, friction, compliance, and
  camera/board uncertainty.
- Whether motor current/effort is available and calibrated on the reviewed
  physical gateway.
- Provider-backed model roster, prices, and API availability for paper runs.

## Evidence standard

Every slice records changed files, commands, tests, generated receipts, proof
class, limitations, blockers, and next action. A passing simulator reward alone
is never called sim-to-real evidence. Generated correction success is data
generator evidence; only separately frozen policy evaluation is learned-policy
evidence.

## Execution rhythm

1. Read this file, the active brief, live project state, and Git state.
2. Select the smallest unfinished task that advances the current milestone.
3. Add a deterministic rejection or acceptance test first when practical.
4. Implement without touching unrelated dirty files.
5. Run focused validation, then the broadest proportionate check.
6. Update this ledger and the run log with exact evidence.
7. Review against milestone gates and choose `CONTINUE`, `NUDGE`, `REDIRECT`,
   `STOP`, or `ESCALATE`.
8. Continue until L6 passes; never close merely because a partial slice works.

## Progress ledger

```text
Current milestone: L6 - End-to-end proof and closeout complete
Completed: T00-T11
Evidence: exact corrective full replay; 561 suffix-only rows; byte-bound CPU ACT fixture checkpoint; matched Inspect task and deterministic controls
Remaining: separately authorized real-data posterior, provider model campaign, learned-policy held-out evaluation, and physical validation
Blockers: none for hardware-free implementation
Next step: freeze a provider/model campaign or collect evaluator-owned real anchors; neither is implied by this completed infrastructure goal
```
