# sim2claw Goal

Status: `IN_PROGRESS_OR19_CANONICAL_RESET_DYNAMIC_REPLAY`

## Active mission

Advance `observable_registration_contact_causality_v1` without crossing the repository's proof,
hardware, held-out, training, promotion, or paid-compute boundaries.

## Current milestone

`OR19_EXACT_ACTION_DYNAMIC_REPLAY_AFTER_CANONICAL_RESET_REPAIR`

## Current card

`OR19` — canonical rank-1-near reset plus exact-action dynamic consequence

## Current evidence

- OR18 artifact: `36057bb69f0da745418c4d61b44d6ff76480539aa806fe36de779d715bf9f37e`.
- Frozen contract: `configs/evaluations/observable_registration_unilateral_push_dynamic_replay_v1.json`.
- Proof class: `retrospective_outcome_informed_exact_action_simulator_diagnostic`.
- Static contact is clear through sample `224`; the named moving jaw first contacts the pawn at sample `231`.
- The legacy reset-layout composition placed `tan_pawn_e8` at canonical D1; OR19 uses the hardcutover current-workcell reset and fails closed on any initial non-board overlap.

## Authority

All current external authorities are false: `camera_open, gateway, heldout_open, paid_compute, physical_motion, serial, simulator_promotion, task_attempt, training, transfer_claim`.

## Canonical sources

- Current-state map: `configs/agent/current_state_v1.json`.
- Campaign graph: `configs/sail/observable_registration_current_graph_v1.json`.
- Campaign queue: `docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`.
- Historical narrative: `docs/history/GOAL-through-or10-20260729.md`.

## Next transition

`run_formal_write_once_exact_action_dynamic_replay_and_bind_contact_progress_outcome`

## Stop conditions

- Do not start an Executor write turn without a non-null active card and
  an exact role-context packet that grants the required paths and operations.
- Stop on identity drift, widened authority, missing closeouts, or a failed
  `uv run --locked sim2claw check --profile agent`.

## Human constraints

- External service and fresh authority remain user-owned prerequisites.
- Repository evidence outranks historical prose and advisory research.
