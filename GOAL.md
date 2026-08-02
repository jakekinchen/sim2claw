# sim2claw Goal

Status: `OR50_PASS_QUARANTINED_NUMERIC_TASK_REPLAY_EVENT_MISMATCH_REMAINS`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR50_OUTCOME_INFORMED_UPRIGHT_BASIN_REFINEMENT`

## Current card

`none` — the campaign is at an external-input boundary

## Current evidence

- Closeout: `configs/decisions/observable_registration_outcome_informed_upright_basin_v1_closeout.json`.
- Closeout SHA-256: `38a5cdf33938bad8949ae836e043028c9c3cc871154cbe38eaca4b9d4e460a1a`.
- Proof class: `quarantined_outcome_informed_exact_episode_natural_dynamics_upright_basin_refinement`.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`preserve_or50_terminal_success_and_freeze_any_event_residual_successor_as_a_new_quarantined_card_or_resume_or48_after_external_metric_inputs`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
