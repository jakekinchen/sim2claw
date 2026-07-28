# Slice Brief 056 - d1 d2 direct stable anchor recovery

**Date:** 2026-07-27

**Status:** Terminal safe stop; recovery tracking acceptance failed.

## Objective

Execute at most one independently reviewed recovery-only route from the fresh
out-of-range torque-off elbow to a previously stable torque-off geometry,
using the elbow value recovery v1 actually reached and omitting its deeper
unreachable request.

## Acceptance Criteria

- Recovery v1 and all earlier camera/setup receipts remain unchanged.
- Fresh follower identity and torque-off anchor match the compiled packet.
- The setup clamp changes elbow only, inward, by at most `3°`.
- One `481 x 6` little-endian float64 route first moves only elbow to the
  physically reached `93.934066°`, then moves the other five joints to
  `[-0.791209, -105.758242, 93.934066, -100.000000, -119.076923, 1.662708]`.
- Elbow is monotonically non-increasing from the in-range command anchor to
  `93.934066°`; the rejected `90.614424°` request is absent.
- CPU/fp64 preview covers the setup-clamp hyperrectangle and every route row,
  reports no new or worsened source contact, no external contact, and clears
  source-only model contact at the destination.
- C922, native D405 RGB, and Pi IMX708 start before motion, enclose the route,
  report no material drops, and clean up.
- No pawn, board, table, or unrelated object contact is observed.
- No route-row clamp, rate limit, stall, assistance, intervention, IK, offset,
  or corrective suffix occurs.
- Torque is disabled on closeout.
- A fresh configuration-free postflight anchor is inside every calibrated
  limit and can be consumed by the exact gateway without clipping.

## Expected Files

- `configs/hardware/prospective_d1_d2_elbow_sag_recovery_tricam_v2.json`
- Ignored packet, review, camera media, ledger, and receipts under
  `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v2/`
- `docs/session-logs/038-executor-d1-d2-direct-stable-anchor-recovery.md`
- `docs/reviewer-messages/036-d1-d2-direct-stable-anchor-recovery.md`

## Validation

- `uv run --locked sim2claw wrist-view-reposition --phase compile ...`
- `uv run --locked sim2claw wrist-view-reposition --phase review ...`
- `uv run --locked sim2claw wrist-view-reposition --phase execute ...`
- `uv run --locked pytest -q tests/test_wrist_view_reposition.py tests/test_pi_motion_video.py`
- `scripts/audit_autonomous_workflow.sh`

## Evidence Boundaries

This slice is recovery/setup only. It cannot change Twin fidelity, task score,
or prove task/transfer success. Its only promotion gate is a fresh in-range,
torque-off exact-task anchor.

## Stop Conditions

- Hardware identity, fresh anchor, action bytes, or camera readiness drift.
- Unsafe scene, cable, contact, or geometry.
- Any clamp inside the frozen route, rate limit, stall, tracking failure,
  action mismatch, or camera loss.
- Torque-off closeout cannot be verified.

## Downstream Gate

Only a passing reviewer decision may activate a completely new prospective
D1→D2 REAL→SIM task action from the fresh stable anchor. SIM→REAL remains
forbidden until that physical and physics task pair both succeed.

## Outcome

The one reviewed execution stopped safely after `263 / 481` frozen motion
rows. The last persisted elbow request was `93.934066°`, the observed elbow
was `97.186813°`, and the no-progress duration was `0.975 s`; the next planned
row hit the one-second stall-warning boundary before persistence.

All persisted rows retained exact requested/sent identity, C922, native D405
RGB, and Pi enclosed the action, no pawn/board/table contact was observed, and
torque-off plus camera cleanup were verified. The fresh torque-off elbow is
inside the calibrated envelope at `101.670330°`, but the route did not
complete without a stall. Recovery tracking therefore failed acceptance and
the downstream task slices remain closed.
