# sim2claw Goal

Status: `COMPLETE_OR11_EXACT_CONTACT_PHASE_NEGATIVE_BLOCKED_EXTERNAL_METRIC_ANCHOR`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR11_COMPLETE_EXACT_CONTACT_PHASE_NEGATIVE_BLOCKED_EXTERNAL_METRIC_ANCHOR`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_contact_phase_registration_v1_closeout.json`.
- Closeout SHA-256: `76bdbd096119ba190ac8bdf6cee24b94bac027cb33819a4e20cb851a2177e086`.
- Proof class: `exact_applied_state_named_geom_kinematic_contact_phase_gate_no_fit_no_dynamics`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`external_robot_base_to_board_metric_anchor_v1_or_post_service_or9_four_pose_no_contact_validation_then_one_frozen_candidate`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
