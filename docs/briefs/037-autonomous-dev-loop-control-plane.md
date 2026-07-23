# Brief 037: canonical autonomous development control plane

## Milestones

Advance D1 and D2 from
`docs/goals/AUTONOMOUS_DEV_LOOP_OPS_AND_ADVANCEMENT_PLAN.md`.

## Required outcome

Implement a deterministic repo-local development-loop package that validates
canonical state, renders/checks the current ledger block, detects authority
drift, issues content-addressed task/review/test/process receipts, permits test
reuse only for exact identities, safely cleans verified expired processes, and
emits a merge-readiness packet without granting release or external authority.

## Allowed paths

- `src/sim2claw/dev_loop/**`
- `src/sim2claw/cli.py`
- `tests/test_dev_loop_*.py`
- `tests/fixtures/dev_loop/**`
- `configs/dev_loop/**`
- `scripts/audit_dev_loop.sh`
- current goal/state/ledger and this slice's session/reviewer records

## Frozen boundaries

- One writer in the checkout.
- Local `main` and `origin/main` were equal at D0 commit `f5ee4c9`.
- No provider, Brev, training, simulator campaign/promotion, physical capture,
  gateway, or robot motion.
- Never signal a process without matching its stored PID start token and repo
  ownership.
- Never reuse a test receipt unless commit tree, runtime, dependency, command,
  and relevant-input identities match exactly.
- The ledger is history plus one generated current block; canonical machine
  state remains in `project_state.json`.

## Verification

- Positive canonical-state audit on the live checkout.
- Negative fixtures for plan/goal hash, branch/remote, milestone, ledger, and
  authority drift.
- Receipt tamper and changed-identity tests.
- One-writer/duplicate lease rejection.
- PID mismatch refusal, verified expired-process cleanup, and crash resume.
- Merge-readiness packet stays all-false for release/external authorities.
- Focused CLI and package tests.

DevLoopBench is a deterministic configured control-label coverage probe over
seeded fixtures. It does not execute every named validator and does not measure
general agent intelligence, coding quality, or research effectiveness.

## Stop conditions

Stop for unrelated user changes, unexpected branch/remote divergence, an
unverifiable process identity, or a required external authority. Ordinary
implementation/test failures are repair work, not blockers.
