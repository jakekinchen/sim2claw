# D1→D2 wrist-dominant setup and exact-task preflight

Date: 2026-07-27

Campaign: `20260727-d1-d2-wrist-dominant-setup-v2`

Outcome: `scene_admitted_task_start_blocked_before_torque`

Proof class: `prospective_exact_task_preflight_terminal_blocker`

## V1 preservation

Camera-pose setup v1 remains terminal and was not retried or mutated. Its
route, packet, review, and execution-receipt SHA-256 values remain:

- `00876cf9edf5981e65b0098554514e82a79b11a919156a1d6b35b2e84c3124f8`
- `5b44df20f3f503d9d25de896dd4515e4c76f419e3aedb1d3f9f9f2e16fcf8553`
- `7828fb65f96942d57002712989d1f89623cd6d94b75569d78dabeea8f891181f`
- `f269b9809891385e62b7b3b6b4fe310f5d58a62950af502ff8266419178a1457`

## Wrist-dominant setup review

A fresh configuration-free preflight observed this stable torque-off anchor:

```text
[-6.857143, -89.582418, 104.483516, -40.835165, -101.054945, 1.662708]
```

The new candidate held pan, lift, elbow, and gripper exactly at those values
and moved only wrist flex and wrist roll toward the previously evidenced
sample-99 board-view orientation.

The candidate was rejected before packet creation and before torque. The live
elbow anchor is `104.483516°`, while the calibrated upper limit is
`102.109890°`. The existing exact compiler correctly returned:

`reviewed wrist-view waypoint exceeds fresh calibrated limits`

Replacing the live elbow value with the upper limit would command `2.373626°`
of elbow motion and would change the frozen wrist-only candidate. No such
substitution, clipping, setup recovery, or motion was attempted.

## Explicit D405 downgrade and fresh camera evidence

The allowed fallback was applied. One motion-free degraded tricam transaction
was captured with no robot gateway construction:

- C922 owns board occupancy and final-square evidence.
- Pi IMX708 owns external robot context.
- D405 is action-enclosing supporting RGB only.
- `metric_depth=false`; `depth_channel_available=false`.

All three streams enclosed the three-second readiness interval:

- C922: exact device, 151 frames, zero Apple drops, zero writer backpressure,
  zero inferred missing intervals.
- D405: exact device, 25 frames, zero Apple drops, zero writer backpressure,
  zero inferred missing intervals.
- Pi IMX708: 230 frames at 1536×864 and 30 fps.

The current C922 frame was compared side by side with the prior Phase A source
start and end. It matches the visually verified D1-start occupancy, not the D2
outcome. The scene reviewer therefore admitted an upright pawn at D1, empty
D2, and the visible carry corridor. Pi shows the arm high and contact-free.
D405 still shows the ceiling and partial gripper arms, so it has no board,
occupancy, or task-outcome authority.

Evidence hashes:

- transport receipt:
  `61c8331c298d43650122631b32ddf6d55b96cc186d012c8963f4b14315589601`
- scene review:
  `85bd06d98fa615bb9130f450738414035f89f973c4d07aad9085d2a097695ec6`
- C922 start/current/end comparison:
  `68169def1a50ba7d7120ab536a0ca372d697833dedf0e1a456bac63e55a3ec99`

## Exact task-start review

Camera downgrade removed the visual blocker but did not admit an action.

The successful D1→D2 source starts as much as `59.252747°` away from the fresh
anchor. The closest observed source row is still `22.593407°` away in the
maximum joint and was itself rate-limited and safety-clamped; it is also not
the task start.

There is therefore no exact, unmodified task start at the live anchor. Reaching
the demonstrated start would require another large setup or a forbidden
offset, clipping operation, retiming, action repair, or setup prefix. The
campaign stopped before:

- freezing canonical task bytes;
- issuing an action hash;
- independent task-execution approval;
- simulator task preview;
- task gateway construction or torque;
- pawn contact or physical task motion.

The ignored task preflight receipt is:

`runs/prospective-real-to-sim/20260727-d1-d2-wrist-dominant-setup-v2/task_action_preflight_receipt.json`

SHA-256:
`311c9cca2287e4e765ca6764e681a0b7275d55e2adb86d14b389e4482d5df00a`

Phase 1 did not run or pass, so Phase 2 remains forbidden. Final independent
preflight reported `physical_follower_torque_enabled=false`, no camera process
remained, and the device configuration was not rewritten.
