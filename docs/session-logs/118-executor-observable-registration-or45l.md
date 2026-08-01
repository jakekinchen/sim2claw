# Executor session 118 — OR45L camera-only lease control plane

Date: 2026-08-01
Card: `OR45L`
Result: `PASS_CONTROL_PLANE_READY_NO_DEVICE_ACCESS`

OR45L adds a separate one-shot capability representation instead of setting
the persistent campaign's `camera_open` authority to true. The capability:

- binds clean synchronized `main` and rejects repository drift;
- verifies the committed OR44 recorder binary hash;
- binds the reconciled D405 SDK serial `130322273474` while preserving the
  distinct ASIC/USB serial evidence;
- freezes the OR45 `30`-frame `424×240 @ 30 Hz` Z16 command and output path;
- expires after five minutes;
- permits one invocation and no adaptive retry;
- consumes itself on success, recorder failure, or evaluator exception; and
- keeps serial, gateway, torque, robot motion, object interaction, task,
  simulation, and transfer authority false.

The capability compiler refuses to mint while the worktree is dirty or local
`main` differs from `origin/main`. This forces the live lease to identify the
exact committed implementation that will consume it.

Validation: `13 passed` across the OR44 sidecar, OR45 evaluator, and OR45L
lease-control tests. No device was enumerated or opened and no camera stream,
robot access, serial access, task attempt, or simulator replay occurred during
this card.

The next action is to commit and push OR45L, re-run the agent workspace check,
mint one ignored five-minute lease, and consume it exactly once.
