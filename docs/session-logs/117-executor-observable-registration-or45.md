# Executor session 117 — OR45 static metric capture readiness

Date: 2026-08-01
Card: `OR45`
Result: `ACTIVE_SOFTWARE_READY_BLOCKED_AGENT_CAMERA_AUTHORITY`

The previously frozen OR45 contract had no evaluator, tests, immutable receipt
writer, or executable one-shot path. Commit `a266f07` adds those missing pieces.

The evaluator now verifies the exact `30`-frame `424×240 @ 30 Hz` D405 Z16
packet, including D405 identity, serial presence, positive metric scale, finite
intrinsics, raw byte and stride/offset completeness, frame indices, unique frame
numbers, strictly monotonic device and host timestamps, and explicit
complete/partial/missing status for optional frame metadata. It intentionally
does not interpret depth as a jaw mapping.

The runner rejects false camera authority before creating its output directory,
requires an exact D405 serial, verifies the committed OR44 binary hash, permits
one invocation with no retry, and emits a terminal receipt on a recorder failure.
It keeps serial, torque, robot motion, task attempts, simulation, mapping, and
transfer claims false.

Validation:

- `14 passed` across focused OR43, OR44, and OR45 tests.
- `5 passed` in the final focused OR45 rerun.
- `ruff` was unavailable in the locked environment and therefore did not run.

No device was enumerated or opened, no camera stream started, and no robot,
serial bus, task, or simulator action occurred. The next card is OR45L, which
must represent camera-only access as a separate expiring one-shot capability
without widening persistent campaign authority.
