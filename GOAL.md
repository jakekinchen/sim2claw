# sim2claw Goal

Status: `COMPLETE_RETAINED_DATA_RECALCULATION_PARTIAL_DYNAMIC_ADVANCEMENT`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR20_CONTACT_CONSEQUENCE_LOCALIZATION`

## Current card

No active card — the retained-data loop is closed at an identified object-dynamics evidence boundary.

## Current evidence

- OR19 artifact: `f33198841ce3e70a11dfc7f2e617174248e436bd18474b3bb626700b6674e184`.
- OR20 artifact: `4374827196aae08617b9899387cbdd31e5bfcd625e773efadbf95229ac908668`.
- Exact actions first make named jaw contact at sample `231`, move the pawn at `248`, and produce `47.513 mm` signed D2 progress.
- The `36.025 mm` progress gate passes and final D2 error is `9.945 mm`, but the pawn tips `102.106°` and collateral displacement reaches `11.451 mm`.
- The remaining causal channel is object orientation/contact consequence. Existing evidence does not identify contact height, mass/COM, friction, or compliance.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`preserve_or19_best_replay_until_independent_metric_orientation_and_contact_force_evidence_exists`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
