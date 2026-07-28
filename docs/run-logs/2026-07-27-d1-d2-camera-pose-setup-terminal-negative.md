# D1→D2 camera-pose setup — terminal negative

Date: 2026-07-27

Campaign: `20260727-d1-d2-camera-pose-setup-v1`

Outcome: `stopped_safely_before_camera_qualification`

Proof class: `physical_camera_setup_only_terminal_negative`

## Scope and frozen setup

This was one prospective, contact-free camera-pose setup attempt. It was not a
task action and had no pawn-contact or transfer authority. The rejected
RGB-only qualification v1 and the public Phase A release were not changed or
rerun.

The terminal target was not visually invented. It was the exact observed
six-joint follower state at sample 99 of the prior physical D1→D2 source, whose
hash-bound D405 frame shows the board and gripper before pawn contact. That
source sample was not rate-limited, clamped, stalled, or in gripper-contact
hold.

- Route:
  `configs/hardware/prospective_d1_d2_camera_pose_setup_tricam_v1.json`
- Route SHA-256:
  `00876cf9edf5981e65b0098554514e82a79b11a919156a1d6b35b2e84c3124f8`
- Frozen motion action SHA-256:
  `d8d8d9d24c7c06f60e7afe6e9eb4f54691e4e89dd5911f6f2769952d0e0b7e3c`
- Frozen terminal hold SHA-256:
  `916d7179ac98fc36902e7873ce7dcea920d20361d9c33c986da39fc252ce47c0`
- Packet SHA-256:
  `5b44df20f3f503d9d25de896dd4515e4c76f419e3aedb1d3f9f9f2e16fcf8553`
- Review decision:
  `ACCEPT-D1-D2-CAMERA-POSE-SETUP-TRICAM-20260727-V1`

The independently reviewed CPU MuJoCo preview found no initial, path, final, or
external contacts and no new or worsened kinematic contact. The setup used a
29.025-second, 40 Hz float64 interpolation with a maximum commanded slew of
3.095112 degrees per second. Clipping, IK, offsets, assistance, manual camera
adjustment, and corrective suffixes were forbidden.

## Single physical execution

The exact follower gateway executed the setup once. C922 overhead RGB, native
D405 wrist RGB, and Pi IMX708 RGB were recording before motion.

The gateway stopped safely after 766 of 1,161 motion samples, before any
terminal-hold sample. At recorded sample 765:

- requested joint bytes equaled gateway-sent joint bytes;
- `rate_limited=false`;
- `safety_clamped=false`;
- `gripper_contact_hold=false`;
- the elbow had made no measurable progress for 0.975 seconds and had
  accumulated 40 consecutive no-progress samples.

The next control step reached the gateway's one-second stall-warning boundary,
so the exact executor rejected continued tracking and closed torque. No retry,
repair, or suffix was attempted.

The last commanded elbow target was 79.120879 degrees; the last observed elbow
position was 82.769231 degrees. The full observed stop pose was:

```text
[-6.945055, -89.758242, 82.769231, -41.450549, -101.318681, 1.662708]
```

After the stop, an independent follower preflight observed the torque-off pose
and reported `physical_follower_torque_enabled=false`. The device configuration
was not rewritten.

## Camera evidence

All three RGB transports completed and enclosed the motion interval:

- C922: exact bound device, 623 callback/browser frames, zero Apple callback
  drops, zero writer backpressure, zero inferred missing intervals.
- D405: exact bound D405 device, 104 callback/browser frames, zero Apple
  callback drops, zero writer backpressure, zero inferred missing intervals,
  `metric_depth=false`.
- Pi IMX708: 1,040 frames at 1536×864 and 30 fps; bounded capture completed.

This transport result does not qualify the camera pose. The terminal D405 frame
still shows the ceiling because the frozen target was not reached. The required
terminal hold showing the gripper, D1, D2, and full carry corridor never
occurred. Scene admission was therefore not attempted.

Terminal review-frame SHA-256 values:

- C922: `c498dd56e038fe1c476bcd3b40336d10118d8b16ed7841e09f14f671a0da96d8`
- D405: `0947e1054321f233c1fd222970ffa435cd91d96b830e8d2c75b4195f5370ecd3`
- Pi: `c06eab295b9e834ef7dd379bc2078c6b30e6a4caa4c1579572e69e304e29d27c`

## Gate result

RGB transport readiness passed, but camera-pose qualification failed. The
prospective D1→D2 task action was not compiled or executed, no pawn was touched,
and REAL→SIM task replay and SIM→REAL remain unattempted. This campaign grants
no task-success, transfer, metric-depth, Twin-fidelity, or bidirectional claim.

The ignored evidence receipt is:

`runs/prospective-real-to-sim/20260727-d1-d2-camera-pose-setup-v1/stage-1/execution_receipt.json`

Its status is `stopped_safely`, it requires
`stop_before_further_robot_command=true`, and it records
`physical_follower_torque_enabled=false`.
