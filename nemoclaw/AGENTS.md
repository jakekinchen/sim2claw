# NemoClaw Sim2Claw operating contract

The mounted Sim2Claw repository and its current files are the authority. Read
`GOAL.md`, `docs/autonomous-workflow/project_state.json`, and the selected
`configs/projects/*.json` before taking project action.

- Treat the frozen evaluator referenced by the project manifest as immutable.
- Preserve fixture, simulation, replay, learned-policy, physical-source, and
  physical-task evidence as separate proof classes.
- Never open held-out rows, admit training data, or promote a checkpoint merely
  because training or an agent reports success.
- Never issue robot, serial, servo, camera, or physical-motion commands. This
  sandbox has no physical authority.
- Require the exact project authority contract: `physical_authority=false`,
  `robot_motion_allowed=false`, `retrospective_recordings_can_promote=false`,
  `training_can_promote_itself=false`, and `held_out_rows_opened=0`. Missing,
  extra, mistyped, or changed authority fields are a hard failure.
- Write generated material only beneath `artifacts/`, `datasets/`, `outputs/`,
  `runs/`, or `checkpoints/`. Do not rewrite source contracts or historical
  receipts.
- Deploy only a reviewed, clean, committed Git HEAD. Never package tracked or
  untracked working-tree dirt, and never treat a historical tarball as current
  source authority.
- Require coordinator-computed outer SHA-256 digests for both archives and
  verify them on the host and inside the sandbox before extraction.
- Run one bounded `sim2claw pipeline-stage` at a time. Report `passed`,
  `partial`, and `blocked` faithfully; a blocked gate is a useful result.

The user-facing reference scope is B-G pawns moving between ranks 1 and 2 in
both directions. A and H are out of scope for the current product claim.
