# Slice Brief 004: Physical Teleoperation Gateway and Simulator Replay

**Date:** 2026-07-18

**Milestone:** physical source infrastructure advanced by owner direction;
physical task proof remains separate

## Objective

Allow the identified physical SO-101 leader to control the identified physical
follower through one fail-closed gateway, save an explicitly unqualified raw
source trace, and replay the follower command trace through MuJoCo for a bounded
joint-response comparison.

The current task scene uses brown source pawns at A2, B1, C2, D1, E2, F1, G2,
H1 and mirrored tan pawns at A8, B7, C8, D7, E8, F7, G8, H7. New simulator
recording and trace-replay paths use that layout.

## Start protocol

1. Identify two distinct saved serial buses and exact calibration hashes.
2. Open both buses with torque forced off and read all six calibrated positions.
3. The operator places both arms in roughly the same physical pose. Sync
   refuses more than 20 degrees of body mismatch, commands the follower to hold
   its current position, then ramps it to the leader pose over 2.5 seconds.
4. Verify the final residual is at most three degrees, verify the leader stayed
   still, and finish Sync with follower torque off.
5. Require the workcell/power acknowledgement and display a three-second
   warning countdown.
6. Command the follower to its synchronized current position before enabling
   recording torque.
7. Capture the leader and follower values as a paired relative zero and begin
   recording only after that registration passes.
8. During recording, retain 4-degree command steps, calibrated joint-limit
   clipping, 90-degree body/180-degree wrist-roll relative excursions, current
   reads, and automatic stop after five seconds without measurable progress or
   immediately on a bus error.

## Evidence boundary

Physical rows retain leader target, requested/sent follower command, actual
follower position/velocity, tracking error, raw available current, clamp state,
rate-limit/stall state, and timestamps. Piece/target poses remain unavailable until a reviewed physical
pose source exists, so these rows are
`physical_teleoperation_source_unqualified` and are not ACT training rows.

The simulator replay applies the recorded physical follower commands to the
current MuJoCo SO-101 and reports joint RMSE/max error. It is a command-response
comparison, not a learned-policy evaluation, object/contact validation, or task
success result.

## Stop conditions

Calibration mismatch, missing/distinct-bus failure, Sync mismatch outside the
guard, post-hold movement, a sustained follower stall, USB dropout, or any
shutdown error stops the run and requests follower torque-off. A rate-limited
follower that advances or resumes within the five-second window does not count
as stalled. Failed samples are retained for diagnosis and do not block Retry.
