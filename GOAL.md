# sim2claw Goal

Status: `IN_PROGRESS_OR14_BELIEF_RECALCULATION`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR14_RECALCULATE_STATIC_ROBOT_BELIEFS_UNDER_OR13`

## Current card

`OR14` — bounded retained-image factor recalculation

## Current evidence

- Predecessor: `configs/decisions/post_hackathon_home_workspace_geometry_camera_v2_closeout.json`.
- Frozen contract: `configs/evaluations/observable_registration_belief_recalculation_v1.json`.
- Proof class: `retrospective_static_image_factor_recalculation_under_owner_metrology_no_task_outcome_no_promotion`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`rank_bounded_robot_side_static_families_then_freeze_at_most_one_exact_contact_phase_candidate`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
