# ACT Source Recorder Setup Smoke

Date: 2026-07-18 America/Chicago

Git baseline before implementation: `4cd52bc`

## Device preflight

- Leader: `/dev/cu.usbmodem5B3D0448141`, expected calibration present
- Follower: `/dev/cu.usbmodem5B3D0406411`, expected calibration present
- Ignored non-motor device: `/dev/cu.usbmodemSN234567892` (USB Billboard)
- Runtime: LeRobot `0.6.0`
- Simulator follower mode: ready
- Physical follower: device-present, control unavailable pending the reviewed
  gateway and ACT-7/M13 prerequisites

## Rendered workflow proof

The Record view was inspected at desktop and mobile sizes with no horizontal
overflow or browser-console error. Start opened the leader bus with torque
disabled and drove only `mujoco:left_so101`. While recording, `lsof` reported
the leader serial port open by Studio and no open handle on the physical
follower port. After Stop, neither motor bus had an open handle.

The saved setup smoke artifact is:

`datasets/act_source_recordings/setup-smoke-sim-leader__20260718T175501Z-12d6d148`

- source rows: 326
- samples SHA-256:
  `11b6159ef60d2ed98239c5ec8abaa8f4725de88c9a511b5c22a21869c93b3f9c`
- label: `setup-smoke-sim-leader`
- outcome: `unreviewed`
- physical follower torque recorded: false
- training data: false
- admission: pending deterministic replay and separate evaluator
- Git handling: ignored by the repository `datasets/` rule

This was an idle/setup capture, not a task attempt. It proves the local
leader-to-MuJoCo recording path and file placement only; it is not a successful
demonstration, training row, learned-policy result, or physical task proof.
