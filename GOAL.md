# sim2claw Goal

Status: `BLOCKED_EXTERNAL_METRIC_SENSOR_AND_JAW_MARKERS`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR48_EXTERNAL_METRIC_PAD_SURFACE_PACKET`

## Current card

`OR48`

## Current evidence

- Closeout: `configs/decisions/observable_registration_external_metric_pad_surface_packet_v1_closeout.json`.
- Closeout SHA-256: `f6b774da2ea7e09ec1ee5ec34f927390f5a4f913a4cafd994308f53716752c34`.
- Proof class: `static_fail_closed_external_metric_pad_surface_experiment_packet_and_sensor_preflight`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`owner_reconnects_or_replaces_d405_and_provides_two_rigid_jaw_bound_metric_landmarks_then_new_or48_zero_motion_lease_review`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
