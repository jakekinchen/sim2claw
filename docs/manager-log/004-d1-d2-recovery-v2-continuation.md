# Manager Log 004 - d1 d2 recovery v2 continuation

**Date:** 2026-07-27

## Trigger

The owner explicitly authorized continuation through all remaining gated
slices after recovery v1 stopped safely. Recovery v1 and its receipts remain
terminal and immutable.

## Evidence Read

- `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/`
- `docs/session-logs/037-executor-d1-d2-elbow-sag-recovery.md`
- `docs/reviewer-messages/035-d1-d2-elbow-sag-recovery.md`
- `runs/geometric-microtransfer/20260727-geometric-sag-to-stable-anchor-recovery-tricam-v2/`
- Fresh configuration-free preflight on 2026-07-27, which reproduced
  `[-6.769231, -91.164835, 103.956044, -46.197802, -102.813187, 1.662708]`
  with follower torque disabled.

## Diagnosis

`REDIRECT`, evidence anchor `100`.

Recovery v1 proved that the elbow moves inward under the reviewed setup
mechanism, reaching `93.934066°`, but its frozen route then held a deeper
`90.614424°` request long enough to trip the one-second no-progress boundary.
That deep preload is not needed. Recovery v1 physically reached
`93.934066°`, and the other five joints can then move immediately into the
camera-pose v1 geometry previously observed torque-off with elbow
`99.296703°`, inside the exact-gateway envelope.

## Intervention

Authorize one new, separately frozen recovery campaign:

1. preserve recovery v1 byte-for-byte;
2. admit the current out-of-range elbow only as the recovery source;
3. preview the bounded inward setup clamp and one direct CPU/fp64 route;
4. move elbow monotonically only to the physically reached `93.934066°`
   value, then move the other joints immediately into the previously stable
   torque-off geometry while holding that reachable elbow request;
5. start all three RGB cameras before motion and close torque off;
6. require a fresh postflight anchor inside every calibrated limit before
   activating the exact D1→D2 task.

The recovery bytes remain excluded from every task hash and transfer claim.

## Follow-Up

Reviewer brief:
`docs/briefs/056-d1-d2-direct-stable-anchor-recovery.md`

Slice B and Slice C remain fail-closed until their predecessor gates pass.

The one authorized execution stopped safely at the elbow one-second
no-progress boundary after `263 / 481` rows. It did leave an in-range
torque-off elbow at `101.670330°`, but exact recovery tracking did not qualify.
The campaign is terminal, and Slice B/C remain closed.
