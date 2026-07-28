# Manager Log 006 - D1→D2 elbow tracking redirect

**Date:** 2026-07-27

## Decision

`PROCEED_WITH_ONE_MECHANISM_SPECIFIC_CONTACT_FREE_QUALIFICATION`

Evidence anchor: `100`.

## Evidence read

- Immutable recovery v1/v2 and camera-pose setup v1 packets, joint ledgers,
  and terminal receipts.
- Old successful D1→D2 observed-state provenance.
- Fresh configuration-free torque-off preflight.
- Two read-only servo-health inventories with 300 successful register reads
  and 300 successful pings across all six servos.
- Live LeRobot follower calibration and installed SOFollower source.

## Classification

The current servo bus is clean: all six servos enumerate as model 777,
firmware 3.9, status zero, torque disabled, and approximately 12.1-12.2 V.
The elbow is ID 3, not ID 4. The earlier ID 4 incorrect-status-packet event
belongs to wrist flex and the LeRobot configuration-time torque cycle, which
the reviewed exact gateway intentionally bypasses.

The elbow's prior slow inward traces track until command error stabilizes just
above the 3° stall-candidate boundary. That signature, together with prior
successful traversal to `44.527473°` at much higher observed rates, supports a
trajectory/controller/load interaction rather than a dead actuator or current
communications owner.

## Authorized executor slice

Compile, preview, independently review, and execute once the elbow-only
qualification in
`configs/hardware/prospective_d1_d2_elbow_tracking_qualification_tricam_v1.json`.
The route is a new action, not a retry or suffix. It changes only the tested
mechanism: two seconds at `8.335165°/s`, followed by a separately bound
`0.25 s` camera hold, with every existing exactness and safety gate intact.

No pawn contact is authorized in this slice. The follower must be torque-off
after every exit.
