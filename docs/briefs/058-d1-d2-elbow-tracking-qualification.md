# Slice Brief 058 - D1→D2 elbow tracking qualification

**Date:** 2026-07-27

**Status:** Terminal mechanism qualification; physical tracking passed, but
the short D405 hold-alignment gate stopped the campaign safely.

## Objective

Qualify one contact-free inward elbow corridor from the fresh torque-off
anchor, using a mechanism-specific trajectory that does not repeat the slow
commands from immutable recovery v1/v2 or camera-pose setup v1.

## Bound hypothesis

Read-only health rejects a current ID, firmware, voltage, temperature,
hardware-status, or packet-transport fault. Servo ID 3 is `elbow_flex`; the
historical ID 4 `Torque_Enable` status-packet failure belongs to `wrist_flex`
and occurred in the LeRobot configuration path that the reviewed exact gateway
does not call.

The prior inward routes moved at roughly `1.05-1.68°/s` and accumulated a
steady `3.25-3.65°` lag. The gateway's unchanged one-second stall-warning gate
then rejected the route. Historical physical observations prove that this
elbow has traversed the task corridor at materially higher speed. This slice
therefore tests one precompiled elbow-only route from `101.670330°` to
`85.000000°` over 80 fixed intervals at `40 Hz`, or `8.335165°/s`.

## Acceptance criteria

- Start from the fresh exact six-joint torque-off anchor and current hardware
  identity without rewriting device configuration.
- Hold pan, lift, wrist flex, wrist roll, and gripper at the exact anchor.
- Freeze 81 little-endian float64 rows before motion.
- CPU/fp64 preview admits only source-bounded robot self-contact that clears
  monotonically; no pawn, board, or table contact is allowed.
- C922, native D405 RGB, and Pi IMX708 start before motion; D405 depth remains
  unnecessary and no metric-depth claim is made.
- Independent review binds route, packet, action hash, identities, camera
  contract, exact gateway, no clipping/rate/offset/repair semantics, and
  torque-off close.
- Execute at most once. Stop on camera loss, clamp, rate limit, bus retry,
  tracking error, stall, action mismatch, or contact risk.
- A pass requires the terminal torque-off elbow anchor to be inside calibrated
  limits and consumable without clipping by the exact task gateway.

## Evidence boundary

All bytes in this slice are diagnostic/setup recovery only. They are excluded
from every REAL→SIM and SIM→REAL action hash and cannot prove pawn motion,
task success, fidelity, or transfer.

## Result

The exact 81-row action was physically executed once. All action and hold rows
were sent without clamps, rate limits, retries, or stalls. Elbow flex reached
`88.395604°` against the `85.000000°` target, inside the reviewed `5°` final
tolerance. C922, D405 RGB, and Pi enclosed the action with zero material drops.
The campaign stopped safely because the `0.25 s` terminal hold contained fewer
than two 5 Hz D405 frames; it was not retried.

After torque-off, gravity sag returned the elbow to `105.538462°`, outside the
`102.109890°` calibrated gateway envelope. This proves an inward torque-on
tracking corridor and localizes the remaining mechanism to torque-off sag, not
servo identity, communication, thermal, voltage, or torque-on tracking.

## Next gate

Use one reviewed torque-on transaction containing an excluded recovery/setup
prefix followed by a separately hash-bound counted D1→D2 task suffix. Do not
require an impossible torque-off in-range dwell between those boundaries.
