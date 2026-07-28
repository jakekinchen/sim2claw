# Brief 051: tricam vertical geometric validation

Status: completed; actuator gap reproduced
Branch: `codex/geometric-microtransfer-20260727`
Proof target: one prospective, no-contact, 15 mm simulator-derived vertical
move replayed byte-identically on the follower while C922, D405, Pi IMX708,
joint encoders, and motor-current telemetry are all live.

## Why this probe

The 7.5 mm route exposed direction- and load-dependent undertravel rather than
a remaining rigid geometry error. A fresh action-frozen replay retained the
general deadband direction but rejected the old elbow load-bias term. The
vertical move is the smallest current-anchor action that:

- is contact-clean in the current MuJoCo scene;
- has `0.627 mm` IK residual;
- commands meaningful, mixed-direction pitch motion
  (`+2.842°` lift, `-6.395°` elbow, `+4.141°` wrist flex);
- leaves pan, wrist roll, and the gripper essentially unchanged;
- stays inside calibrated limits and below the existing 10°/s slew ceiling.

## Frozen observation requirement

Use `native_motion_tricam`. The action may not begin until the native C922/D405
session and bounded Pi stream are both live. The camera interval is motion
start through the final torque-on hold plus 250 ms post-roll. Reject the
physical receipt unless all three streams enclose that interval and retain
their source videos, browser copies, callback/PTS ledgers, and hashes.

A camera-only rehearsal already completed with 74 C922, 13 D405, and 230 Pi
frames; all three enclosed the rehearsal interval. The C922 sees the board,
pawns, and arm. The Pi sees the full arm, link tags, and part of the board.
The wrist D405 currently sees the gripper silhouette against the ceiling; it
is still retained because it observes wrist-local divergence.

## Execution and stop conditions

1. Compile from a fresh torque-off follower read.
2. Seal one independent review receipt.
3. Execute exactly one 361-row float64 interpolation plus the frozen 80-row
   hold.
4. Stop torque-off after the stage regardless of outcome.
5. Reject on changed action bytes, camera start/liveness/enclosure failure,
   new simulator contact, clamp, rate limit, stall, serial/identity drift, or
   final joint residual outside `[3°, 3°, 5°, 3°, 3°, 5]`.
6. Do not touch a pawn in this transaction.

## Decision

Replay the resulting trace through only the rigid actuator, prior two-degree
deadband, and already rejected load-response variants. No variant may change
the physical action. Retain the simple deadband direction only if it improves
both joint and end-effector RMS against rigid on this prospective stage.
Otherwise fit one direction/load-conditioned play family on the accumulated
three stages and require a new held-out geometric action before pawn contact.

## Closeout

The one physical stage completed all 361 motion rows and 80 hold rows with the
frozen action hash
`c489633917fcce98f95124d8dc14290635926fa0248d0a237174c183b766bfd2`.
There was no clamp, rate limit, stall, assistance, intervention, or error, and
the follower closed torque-off.

All three cameras enclosed the full action and final hold:

- C922: 375 native callback frames, zero inferred gaps;
- D405: 63 native callback frames, zero inferred gaps;
- Pi IMX708: 440 frames with a continuous local PTS ledger.

The cameras are concurrent but not hardware exposure-synchronized. The Pi
view detected tags 0, 1, 2, 3, and 6 in every nominal action frame. ID 2
provided the strongest motion signal at about 23 pixels between the pre-action
and final-hold medians. C922 and D405 provided contextual video but no strict
tag detections in this pose.

The final physical residual in joint order
`[pan,lift,elbow,wrist_flex,wrist_roll,gripper]` was
`[0.016,-2.314,2.352,-1.065,0.089,0]°`. The prospective frozen evaluation
showed that the prior two-degree lift/elbow deadband improved joint RMS by
`53.0%` and end-effector RMS by `49.5%` over a rigid actuator on this trace.
The old additive elbow load-bias variant worsened both metrics relative to the
plain deadband and remains rejected.

The accumulated three-stage bounded fit selected a `1.5°` lift, `2.0°` elbow,
and `1.0°` wrist-flex deadband. It is not promoted; Brief 052 freezes a
separate physical out-and-back to test the missing reverse directions before
any pawn contact.
