# sim2claw Goal

Status: `OR150_COMPLETE_MOBILE_LEGIBLE_DISCLOSURE_OR149_OR148_TERMINAL_BOUNDARIES_RESTORED`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR150_COMPLETE_MOBILE_LEGIBLE_DISCLOSURE_OR149_OR148_TERMINAL_BOUNDARIES_RESTORED`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_registration_d1_d2_nominal_wrist_mobile_readability_v1_closeout.json`.
- Closeout SHA-256: `f48bf4ee4b8f160aeec3679a2b3a6089f200fa2599e701dbb0a9376117df2a24`.
- Proof class: `presentation_only_burned_disclosure_mobile_readability_derivative`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`None`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
