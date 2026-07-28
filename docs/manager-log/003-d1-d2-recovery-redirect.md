# Manager Log 003 - d1 d2 recovery redirect

**Date:** 2026-07-27

## Trigger

The RGB-only camera gate passed, but the prospective exact-task campaign
stopped because the follower relaxed torque-off to elbow flex
`104.483516°`, outside the calibrated exact-gateway upper limit
`102.109890°`. The old D1→D2 demonstration start is also stale and differs
from the live anchor by as much as `59.252747°`.

## Evidence Read

- `runs/prospective-real-to-sim/20260727-d1-d2-camera-pose-setup-v1/`
- `runs/prospective-real-to-sim/20260727-d1-d2-wrist-dominant-setup-v2/`
- `docs/run-logs/2026-07-27-d1-d2-camera-pose-setup-terminal-negative.md`
- `docs/run-logs/2026-07-27-d1-d2-wrist-dominant-task-preflight-terminal.md`
- Existing completed gravity recovery:
  `runs/geometric-microtransfer/20260727-geometric-sag-to-stable-anchor-recovery-tricam-v2/`
- Fresh configuration-free preflight on 2026-07-27, which reproduced the
  same torque-off anchor and confirmed torque disabled.

## Diagnosis

`REDIRECT`, evidence anchor `100`.

Camera transport and scene admission are no longer the blocking mechanism.
Trying to align to the stale demonstration start conflates recovery/setup
motion with counted task bytes. The current actionable mechanism is
out-of-envelope torque-off sag, for which the repository already has a
bounded, tricam-first setup-clamp and frozen recovery route pattern.

## Intervention

Activate exactly one recovery-only slice:

1. admit the raw out-of-envelope elbow only as the recovery source;
2. preview the explicit ≤3° inward setup clamp and full route on CPU/fp64;
3. move monotonically inward through the previously executed elbow-clearance
   value to the previously observed contact-free torque-off geometry;
4. keep every recovery byte outside task hashes and task claims;
5. require independent review, tricam-before-motion, one attempt, and
   torque-off closeout.

Only a fresh in-range torque-off anchor may activate the new D1→D2 task slice.
The task must be derived from that anchor and must not reproduce the old start.

## User-Facing Impact

The next physical action is a bounded recovery, not a transfer attempt. A
successful recovery removes the gateway-envelope blocker while preserving an
honest task denominator. A failed recovery is terminal evidence for Slice A
and cannot be repaired or retried within that campaign.

## Follow-Up

Reviewer brief:
`docs/briefs/055-d1-d2-out-of-envelope-recovery.md`

Executor result:
`docs/session-logs/037-executor-d1-d2-elbow-sag-recovery.md`

Reviewer decision:
`docs/reviewer-messages/035-d1-d2-elbow-sag-recovery.md`

The one admitted recovery stopped safely at the elbow no-progress boundary and
did not produce an in-range torque-off anchor. The redirect is terminal;
Slices B and C remain closed.
