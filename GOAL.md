# sim2claw Goal

Status: `OR152_TERMINAL_NO_TASK_OUTCOME_METRIC_ADVANCEMENT_NO_RETRY`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR152_TERMINAL_NO_TASK_OUTCOME_METRIC_ADVANCEMENT_NO_RETRY`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_registration_or34_board_coordinate_initialization_replay_v1_closeout.json`.
- Closeout SHA-256: `6fa4c5c0ed2acd54cd9067a469bd3d764dabb646dd05ab0198ddb55e570baa1c`.
- Proof class: `one_run_observation_conditioned_or34_geometry_consistent_initialization_natural_dynamics_diagnostic`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`independent GPT Pro and Fable 5 review of the OR152 counterexample may propose a separately frozen factor; OR152 itself admits no retry or automatic successor`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
