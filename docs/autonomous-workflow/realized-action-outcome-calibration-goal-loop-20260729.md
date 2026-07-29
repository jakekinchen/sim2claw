# Realized-Action Outcome Calibration Goal Loop

Status: `ACTIVE_C1_EPISODE_TWIN_BUNDLES`

Created: `2026-07-29`

## Mission

Execute
`docs/autonomous-workflow/realized-action-outcome-calibration-task-queue-20260729.md`
one card at a time until every safe zero-new-physical-data card is verified,
the C6 realized physical-action trajectory replay has an immutable outcome,
and all code, receipts, tests, proof surfaces, commits, and cleanup agree.

## Source of truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. The realized-action outcome calibration task queue.
4. `GOAL.md`.
5. RP04K, RP04L, and RP04M contracts, receipts, and closeouts.
6. Existing physical source receipts and raw hash-bound evidence.
7. Existing evaluator-owned heldouts and campaign graph.
8. This goal-loop prompt.
9. GPT Pro and Fable advice, which remain non-authoritative.

## Intended outcome

The repository contains a reproducible, receipt-backed calibration chain from
retained physical evidence through an identified simulator plant and
episode-independent contact model to one frozen C6 replay of the exact
gateway-sent D1-to-D2 action trace. The result is reported in its exact proof
class without endpoint, observed-state, or observed-mode injection.

## Acceptance criteria

- C0--C8 each have a terminal status, tracked acceptance evidence, and no
  unresolved safe in-scope work.
- C9 is explicitly closed as deferred at the external elbow-service boundary.
- C0 freezes a hash-bound episode corpus and disjoint whole-episode cohorts.
- C1 produces deterministic `EpisodeTwinBundle.v1` artifacts.
- C2 reports independently scoped static residuals without an unidentifiable
  joint refit.
- C2-RP04N is frozen before annotations/simulator comparison and remains an
  action-free diagnostic.
- C3/C3A report supported actuator residuals and first divergence without
  relabeling sample alignment as causal latency.
- C4 preserves action bytes and improves untouched actuator/EE residuals or
  closes as a terminal identified-plant negative.
- C5 admits only cross-episode identifiable contact/object mechanisms or
  closes as a terminal contact-model negative.
- C6 is frozen before one outcome run, consumes no post-initialization physical
  observation, and records pass or terminal negative without gate changes.
- C7 reports measured robustness without inventing distributions.
- C8 makes every input lane, residual, gate, and proof boundary inspectable in
  Studio at desktop and phone layouts.
- Focused tests, workflow audit, diff check, repository cleanup, and scoped
  commits pass; `HEAD` equals `origin/main`.
- No camera, gateway, serial, torque, physical motion, pawn attempt, or paid
  compute is opened by this loop.

## Evidence standard

Every card transition must record:

- changed tracked paths;
- source/config/implementation/receipt hashes;
- exact denominators and proof class;
- tests and validation commands;
- generated ignored artifacts and their tracked closeout;
- known missing observables;
- the next active card or terminal boundary;
- a scoped commit pushed to `origin/main`.

Optimizer convergence, simulated reward, visual plausibility, or a narrower
observation proof never promotes a card by itself.

## Decision status

### Confirmed requirements

- Use only existing physical evidence.
- Preserve physical authority as false.
- The target rung is physical realized action trajectory to matching simulator
  task outcome.
- RP04N is diagnostic and cannot satisfy that rung.
- Exact actions and prior receipts remain immutable.

### Recommended defaults

- Use the current D1-to-D2 episode as the sealed C6 mission episode.
- Use whole older episodes for fit/validation, excluding metadata-conflicted
  episodes unless an evaluator-owned correction exists.
- Prefer the smallest versioned plant/contact mechanism supported by C3A.
- Run C6 before optional robustness/presentation refinements that do not affect
  its admission.

### Open questions

- Whether existing retained episodes constrain a contact mechanism that
  generalizes to the sealed D1-to-D2 source.
- Whether the current task-bounded joint mapping and identified plant can
  reproduce the release/support consequence without observation injection.

These are experiment questions, not user-input blockers.

## Execution rhythm

1. Read the queue, current card, latest receipts, and git state.
2. Choose the smallest deterministic slice that advances only the active card.
3. Add or freeze tests and contracts before opening an outcome.
4. Execute the slice.
5. Record receipt and proof boundaries immediately.
6. Run focused validation and workflow audit.
7. Commit and push only scoped paths.
8. Update this ledger and activate exactly one next card.
9. Continue until all safe cards close.

For a failed gate, preserve the failure and exhaust only prospectively declared
safe alternatives. Do not tune sealed inputs or repeat C6.

## Progress ledger

```text
Current state: ACTIVE
Active card: C1
Completed: C0
Evidence: C0 artifact 232c80bb28cac325f54d829e31fd2b84d12df85df1948d3d8fb5b4fd3e4739d1
Remaining: C1, C2, C2-RP04N, C3, C3A, C4, C5, C6, C7, C8, C9 boundary
Blockers: physical pathway closed at elbow service boundary; not needed for C0-C8
Next step: build deterministic EpisodeTwinBundle.v1 artifacts for the eight cohorts
```

## Stop conditions

Successful close requires every safe card to have a terminal evidence-backed
status and no remaining safe in-scope implementation. A C6 pass records the
new `1/1` realized-action outcome rung. A C6 failure remains terminal unless
C3A had prospectively named one untested cross-episode mechanism.

Do not stop for difficulty, a first simulator negative, or incomplete
infrastructure. Stop physical work immediately because authority is false.
Stop the entire loop only for completion or a genuine external/safety boundary
that prevents all remaining safe cards.
