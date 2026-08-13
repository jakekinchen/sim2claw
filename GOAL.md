# sim2claw Goal

Status: `OR156_ACTIVE_SOURCE_CLOCK_REBINDING_FALSIFICATION`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR156_ACTIVE_SOURCE_CLOCK_REBINDING_FALSIFICATION`

## Current card

`OR156`

## Current evidence

- Proof class: `retrospective_known_result_read_only_source_clock_provenance_and_frame_association_diagnostic`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`execute exactly one read-only OR156 known-result source-clock provenance audit; no replay, retiming, action mutation, fit, correction, or successor selection`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
