# Brief 040 - Guarded wrist-view reposition packet

## Outcome

Provide the smallest follower-only path from the fresh torque-off pose near
`[-4.131868, -106.901099, 99.912088, -106.153846, -74.769231, 2.969121]`
to the reviewed D405 AprilTag-view pose. Freeze the route as three separately
executed direct-interpolation stages so the operator can inspect the wrist view
before each continuation.

## Invariants

- Use only the reviewed follower gateway; never open a leader or camera.
- Freeze little-endian float64 action bytes with no IK, clipping, offsets, or
  corrective suffix.
- Limit each stage to at most 90 degrees per joint and 10 degrees/s.
- Re-read torque-off pose and hardware identity before every stage.
- Preview every exact action in the current MuJoCo scene and reject new,
  external, or worsened contact.
- Close torque after every stage and write packet, review, samples, and
  execution receipts once.
- Require the preceding completed receipt for stages 2 and 3.

## Verification

- Focused unit and regression tests.
- Offline exact-action preview against the current candidate manifest.
- CLI reachability for compile, review, and stage execution.
- Root agent owns any physical execution and camera inspection.
