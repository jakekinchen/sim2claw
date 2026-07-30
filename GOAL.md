# sim2claw Goal

Status: `COMPLETE_OR13_STATIC_GEOMETRY_AND_CAMERA_CENTER_CANDIDATE_NO_CONTACT`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR13_COMPLETE_STATIC_GEOMETRY_AND_CAMERA_CENTER_CANDIDATE_NO_CONTACT`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/post_hackathon_home_workspace_geometry_camera_v2_closeout.json`.
- Closeout SHA-256: `9c32891753a61d407db68467bddc9eac6893e9c86e880528524ae2538697b956`.
- Proof class: `owner_reported_board_object_camera_center_metrology_static_geometry_successor_and_retrospective_orientation_diagnostic`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`independent_robot_base_height_or_articulated_wrist_vertical_registration_then_one_frozen_static_candidate_before_any_dynamics`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
