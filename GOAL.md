# sim2claw Goal

Status: `ACTIVE_D405_STATIC_METRIC_CAPTURE`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR45_D405_STATIC_METRIC_CAPTURE`

## Current card

`OR45`

## Current evidence

- Closeout: `configs/evaluations/observable_registration_d405_static_metric_capture_v1.json`.
- Closeout SHA-256: `a8e249b2ff4786fa241df211032e6783f4b93240a081f48efddce18e6947ae36`.
- Proof class: `preregistered_zero_motion_d405_static_metric_depth_capture_blocked_agent_camera_authority`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`admit_or45_through_hardware_capable_control_plane_then_execute_once`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
