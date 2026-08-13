# sim2claw Goal

Status: `OR154_PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE_NO_RETRY`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR154_PASS_GATE_LEVEL_TASK_OUTCOME_ADVANCEMENT_TASK_NEGATIVE_NO_RETRY`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_registration_or153_exact_d1_center_replay_v1_closeout.json`.
- Closeout SHA-256: `13ded62b32122532bb0ebb0454ed656df9614aaf929d98f7861526e2d2032a76`.
- Proof class: `one_run_observation_conditioned_or34_canonical_d1_center_sensitivity_natural_dynamics_diagnostic`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`no automatic successor; any action-data calibration requires a separately frozen pre-outcome or cross-episode mechanism that addresses transport/contact and passes independent review`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
