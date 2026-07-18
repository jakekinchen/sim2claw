# Physical Recorder Ergonomics and Rate-Limit Recovery

Date: 2026-07-18 America/Chicago

## Operator evidence retained

Two partial physical attempts ended fail-closed and are retained under
`runs/teleop_recordings/failed_attempts/`:

- `20260718T185528Z-460b02cf` retained 163 samples before a follower-bus
  no-status-packet error.
- `20260718T192659Z-503142c3` retained 157 samples before the old gateway
  classified a rate-limited elbow as stalled.

Both archived states report follower torque off. Neither attempt is a saved
physical episode, a task result, training data, or policy evidence.

## Diagnosis

The old gateway combined two restrictions that made normal teleoperation
unnecessarily brittle:

1. Every body joint was limited to a ten-degree excursion from the registered
   start, producing only about twenty degrees of total usable travel.
2. Twenty consecutive rate-limited samples could become a fault even while a
   servo was still making small or quantized progress. At 20 Hz this made the
   outcome depend on the recorder sample rate and could release torque after
   roughly one second.

The second retained trace showed low current and a quantized elbow position;
that is insufficient evidence of a hard obstruction.

## Correction

The reviewed gateway now:

- clips body travel to both a 90-degree relative envelope and the follower's
  measured calibration bounds;
- permits a 180-degree relative wrist-roll envelope and the calibrated gripper
  range;
- advances body commands by at most four degrees per command;
- records rate limiting as telemetry instead of treating it as a fault; and
- releases torque for a stall only after a joint remains meaningfully behind
  and makes less than 0.5 degrees of measurable progress for five seconds.

The recorder now archives a failed attempt and returns directly to `idle`; no
native reset dialog or discard-before-retry sequence remains. B1 to B2 at 20 Hz
is the initial metadata selection, and mode, source, destination, and sample
rate persist in browser-local settings.

Physical mode also exposes one reviewed `Sync follower to leader` operation.
It accepts only a nearby pair, refuses body mismatch over 20 degrees, ramps the
follower over 2.5 seconds, checks the final pose, and finishes with follower
torque off. Physical Start uses the same Sync before its countdown.

## Verification

- Full repository suite: 56 tests and 10 negative subtests passed.
- Rendered Chromium checks: B1 to B2 and 20 Hz defaults, reload persistence,
  no reset/retry control, and no horizontal overflow from 1440 through 320 px.
- Live torque-off preflight: expected leader and follower buses, calibration
  hashes present, 7.8-degree maximum paired offset, zero reported current, and
  follower torque off.

The Sync motion path is fixture-tested but was not invoked as part of this
verification. The next operator-initiated Sync or recording remains the live
validation of that bounded motion path.
