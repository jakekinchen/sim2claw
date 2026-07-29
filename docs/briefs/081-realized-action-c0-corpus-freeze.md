# Brief 081 — Realized-Action C0 Corpus Freeze

Decision: `CONTINUE`

Evidence anchor: `100`

## Active card

C0 from
`docs/autonomous-workflow/realized-action-outcome-calibration-task-queue-20260729.md`.

## Required slice

Implement one deterministic, hash-bound retrospective corpus manifest and
whole-episode cohort split using only existing physical evidence.

The manifest must:

- inventory every eligible retained manipulation episode;
- bind recording receipt, samples, C922/D405 assets when present, and catalog
  lineage;
- preserve requested, gateway-sent, measured, and timestamp availability as
  separate channels;
- classify metadata conflicts, duplicates, superseded episodes, and proof
  ceilings;
- use canonical square names only where an evaluator-owned correction exists;
- freeze disjoint fit, validation, and sealed cohorts at episode granularity;
- reserve the current corrected D1-to-D2 episode exclusively for C6;
- rebuild deterministically with the same canonical digest;
- open no camera, hardware, gateway, serial, torque, or paid compute.

## Verification gate

- Contract and compiler tests pass.
- Every referenced tracked/raw artifact exists and matches its recorded hash.
- No recording ID appears in multiple cohorts.
- The sealed C6 mission episode is absent from fit and validation.
- Metadata-conflicted older episodes are not silently relabeled.
- A tracked closeout binds the generated ignored receipt.
- Workflow audit and diff check pass.

## Handoff

On pass, update the queue and goal-loop ledger, commit/push C0, and activate C1.
On failure, record the exact missing/provenance boundary and repair only
deterministic inventory defects.
