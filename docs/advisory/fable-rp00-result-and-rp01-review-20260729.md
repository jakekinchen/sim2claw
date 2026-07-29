# Fable RP00 Result Audit and RP01 Review

Status: `CONTINUE_RP01_FREEZE`

Date: `2026-07-29`

Reviewer: Claude Fable 5, effort `High`, existing project thread

Reviewed branch and commit:
`codex/bidirectional-transfer-goal-loop-20260728` at `97e9412`

Review mode: read-only repository inspection. Fable changed no files and
opened no camera, gateway, serial, hardware, or paid-compute authority.

## RP00 verdict

Fable independently accepted the frozen RP00 result:

- the freeze and result commits were remote-equal;
- the contract, receipt, and implementation bindings were intact;
- the grid and two-degree target-selection rule predated the outcome;
- the wrapper changed only the elbow lock and evidence identity while
  preserving the CC03K route compiler and gates;
- `91 deg` retained one statically eligible family per direction, with all
  seven inherited checks passing and no new disallowed robot contacts; and
- the physical and transfer ledgers correctly remained unchanged.

Fable found no material RP00 proof defect.

## Important RP03 caveat

Both currently eligible families push into square `f2`. RP03 must freeze its
direction order prospectively and treat the post-state of the first case as an
exclusion for the second. The second family may therefore become
inadmissible. RP03 must compile against the exact achieved parking angle, not
the nearest RP00 grid cell.

## Exact RP01 freeze requirements

RP01 is a setup/recovery proof class, separately hashed and excluded from all
task-transfer evidence. It does not consume the `0/10` physical task ledger.
It permits one execution only, with no retry absent a new preregistration.

1. Take a fresh configuration-free torque-off read, require all six joints
   inside calibrated ranges, and allow a live rebase only within `1 deg`.
2. Use only a high-clearance setup posture. Across the complete elbow interval
   from the fresh anchor through `91 deg`, require at least `120 mm` clearance
   from the moving chain to the board, pawns, and table and no new self-contact
   beyond the physical corpus envelope. A stall at any intermediate angle must
   remain safe.
3. Freeze this parking ladder for at most twelve requests:
   `request_i = max(91 deg, read_(i-1) - 5 deg)`. Wait `2 s`, then read again.
   Primary success is a read at or below `92 deg`. A final read at or below
   `93 deg` is marginal and requires RP03 at the exact achieved angle. Abort
   after two consecutive iterations with less than `0.3 deg` progress.
4. Record at `5 Hz` for all six servos: goal-position echo, torque-enable,
   present position, current, load, temperature, and status.
5. Hold torque on for `15 s`; require elbow drift no greater than `0.5 deg`
   while retaining current/load telemetry.
6. Start the C922 and Pi cameras before setup and keep them running through
   cleanup. The D405 is optional.
7. Disable torque, then take a configuration-free read after `60 s`.
   Post-torque-off sag greater than `1 deg` is informational rather than a
   transaction failure; every later task start must reverify and trim.
8. Do not execute a return route. The parked posture becomes the new anchor.

The read-conditioned ladder must be disclosed as a control law rather than a
pure frozen row tensor.

## Boundary before physical execution

Before RP02 can open, repository evidence must bind:

- a fresh hardware identity and calibration hash;
- a frozen RP01 contract;
- a full-interval CPU/fp64 safety preview;
- an independent `CONTINUE` verdict;
- the queue and graph transition; and
- explicit owner physical authorization for a bounded execution window.

Any final elbow read above `93 deg` is terminal for this recovery transaction.
The recommended target remains `91 deg`; Fable explicitly rejected changing
it to `90 deg` after seeing RP00.

## Claim boundary

This audit accepts the RP00 simulation-only certificate and authorizes the
RP01 freeze only. It does not authorize cameras, gateway, serial, torque,
physical motion, pawn contact, a task attempt, mapping approval, simulator
promotion, policy-ranking prediction, or transfer.
