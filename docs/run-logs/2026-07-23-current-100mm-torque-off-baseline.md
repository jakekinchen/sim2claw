# Current 100 mm Torque-Off Measurement Baseline

Date: 2026-07-23

Proof class: `physical_torque_off_read_only_baseline`

This is a synchronized hardware-readiness and static-observation result. It is
not a motion, calibration, simulator-improvement, task-success, training,
promotion, or physical-transfer result.

## Frozen execution

The preregistered baseline ran once from committed implementation
`f47e860`. It opened the reviewed SO-101 gateway with follower torque disabled,
captured 30 timestamp-bracketed read-only samples and one C922 diagnostic
video, and closed the gateway. Every row reports
`physical_follower_torque_enabled=false` and
`physical_motion_commanded=false`.

- Samples: `30 / 120` maximum
- Fresh-current samples: `30 / 30`
- Video: 239 frames, 640x480, 30 fps, 7.966667 seconds
- Leader/follower joint range during baseline: 0 degrees on every joint
- Current range: 0 raw units on five joints; 0 to 1 raw unit on wrist roll
- Paired-pose registration: rejected on every row
- Maximum body offset: 97.4945054945 degrees
- Task or empty-gripper cycles: `0`

The camera frame shows the follower over the chessboard and multiple pieces in
the intended workcell. The clear-workcell gate is therefore not admitted.

## Content-addressed evidence

Generated root:
`runs/current-100mm-measurement-20260723/torque-off-baseline-001`

- Receipt file SHA-256:
  `851631b9aca09d7ba5307205f94f4ea5736602846f6d05d456bc4141fdd8ca15`
- Embedded receipt digest:
  `4dbb666ab68fa41688b3d346f54797d947fd0771af8f2ec20edc1ac379eb4021`
- Samples SHA-256:
  `f22d661b1c3563fd5512a6411b150adca71408128123af0bab54a26b455959f1`
- Video SHA-256:
  `a12f50d817948c37315eb85c555f9e224c5a81aa1dc1abfd807c80ad09cab30b`
- FFmpeg log SHA-256:
  `1b15b9bae0e1de128b162148aa8ec5feef765632dc156b5052562b04f28d4dbf`

All 11 frozen S2 artifacts were hash-identical before and after. The retained
campaign remains one event, four action-identical replays, and zero
measurement trials.

## Decision

`baseline_complete_motion_abstained_safe_start_and_workspace_not_ready`

The static pipeline is usable and raw current is fresh, but this zero-load
baseline cannot identify actuator load response, contact/compliance, metric
object pose, or task consequence. Motion remains blocked by two independent
conditions:

1. leader/follower pose mismatch exceeds the reviewed paired-pose guard; and
2. the observed workcell is not clear for an autonomous alignment move.

No parameter, posterior, simulator family, or strict task score changed.
