# Slice Brief 017 - SAIL Retained Evidence Inventory

**Date:** 2026-07-21

## Objective

Complete P1-02 by compiling current repo-native telemetry, action-frozen replay,
video-event, scale, contact, publication, and policy-concordance artifacts into
one deterministic `CalibrationEvidence.v1` catalog and omissions report without
inventing observables or reopening selection.

## Product / Project Value

The catalog becomes the immutable evidence entrypoint for residuals, the belief
graph, the retrospective case study, and TwinWorthiness. It removes scattered
receipt interpretation from later SAIL stages.

## Acceptance Criteria

- Every imported scalar resolves to an exact tracked or ignored source artifact.
- Source bytes, action arrays, simulator/evaluator identities, and regeneration
  commands are bound.
- All 18 physical recordings, 7,741 rows, 11 action-frozen development episodes,
  two already-open confirmation episodes, and major retained campaign receipts
  reconcile or appear in the omissions report.
- 3DGS remains visual-only; AprilTag scale remains nominal-print-conditioned.
- Human teleoperation, GR00T replay, simulation, learned policy, and physical
  outcomes remain separate proof classes.
- Missing channels remain unavailable masks or explicit omissions.
- Repeated compilation is byte-deterministic and GOLD-16 passes when retained
  evidence exists.

## Expected Files

- `configs/sail/campaign_retired_bg_v1.json`
- `src/sim2claw/sail/evidence.py`
- `src/sim2claw/sail/importers.py`
- `src/sim2claw/sail/receipts.py`
- `tests/test_sail_evidence.py`
- ignored `outputs/sail/retired-bg-v1/evidence/`
- P1-02 run/session/reviewer logs

## Test Plan

Start with missing-source, digest-drift, proof-class-confusion, absent-channel,
action-count/hash reconciliation, and deterministic-repeat tests. Use a small
fresh fixture for ordinary CI and the hash-bound retained root for GOLD-16.

## Validation Commands

```bash
uv run pytest tests/test_sail_evidence.py tests/test_sail_contracts.py -q
uv run sim2claw sail-inventory --campaign configs/sail/campaign_retired_bg_v1.json
uv run sim2claw sail-compile-evidence --campaign configs/sail/campaign_retired_bg_v1.json --output outputs/sail/retired-bg-v1/evidence
uv run pytest -q
git diff --check
```

## Evidence To Record

- Campaign config and importer hashes.
- Included, excluded, missing, and already-open counts by proof class.
- Source/action/evaluator reconciliation.
- Catalog, omissions, and receipt hashes plus regeneration commands.
- Focused/broad test results and resource closeout.

## Reachability / Demo Proof

Exercise inventory and compile commands through the existing `sim2claw` CLI and
load the resulting ignored catalog through `verify_contract`.

## Cross-Doc Impact

Update the master-plan ledger, GOAL, project state, orchestration ledger, and
next brief only after GOLD-16 and deterministic recompilation pass.

## Out Of Scope

- Phase alignment and residual values.
- New mechanism fitting or simulator selection.
- Opening sealed or future hardware cohorts.
- Provider calls, paid compute, physical capture, or motion.

## Stop Conditions

- A required retained source is missing or hash-mismatched without an explicit
  omission classification.
- Import requires copying archive or generated artifacts into Git.
- An absent channel would need to be inferred or imputed.
- Action identity or proof-class separation cannot be preserved.
