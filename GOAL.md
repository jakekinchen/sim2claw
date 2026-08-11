# sim2claw Goal

Status: `OR153_PASS_TASK_OUTCOME_METRIC_ADVANCEMENT_TASK_NEGATIVE_NO_RETRY`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR153_PASS_TASK_OUTCOME_METRIC_ADVANCEMENT_TASK_NEGATIVE_NO_RETRY`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_registration_or34_canonical_yaw_reversion_replay_v1_closeout.json`.
- Closeout SHA-256: `e977a57df5db0224213936b0442d34030dc6b81430bfd1fac2b613c87b6f40f0`.
- Proof class: `one_run_observation_conditioned_or34_board_consistent_canonical_yaw_reversion_natural_dynamics_diagnostic`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`no automatic successor; any new factor requires separate owner authority and independent robot-bound metric registration or load-side contact evidence`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
