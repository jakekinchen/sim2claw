# Executor Session 038 - D1→D2 direct stable-anchor recovery

**Date:** 2026-07-27

## Objective

Run one new, separately reviewed recovery-only campaign after terminal
recovery v1, then activate the prospective D1→D2 task only if recovery
completed without a tracking, clamp, rate, contact, camera, or torque fault.

## Frozen Recovery

- Fresh configuration-free torque-off anchor:
  `[-6.769231, -91.164835, 103.956044, -46.197802, -102.813187, 1.662708]`
- Calibrated elbow maximum: `102.109890°`
- Recovery-only setup snap: elbow `-1.846154°`; every other joint unchanged
- Route: `481 x 6` little-endian float64 at `40 Hz`
- Route action SHA-256:
  `45add2c06a672b5bf15c6066c8aa13d320d2eec4f28a0542f614b880947e0f16`
- Packet SHA-256:
  `c4c004ceefc2fa3357cb124e0a358f4d620ed4d3b4a9e81415ea383e6edf6721`
- Review SHA-256:
  `29feb1430b4c9509c6bb4fc66c6d0fc7269871ff59b2c85589b400fd776bfadb`

The route first moved elbow only to `93.934066°`, the value physically
reached in recovery v1, then immediately began moving the other five joints
toward the camera-pose v1 geometry while holding that reachable elbow
request. CPU/fp64 preview admitted the setup-snap hyperrectangle and all route
rows under the bounded source-contact rule. An earlier direct-to-anchor-A
candidate was rejected offline because it worsened source-only model
penetration; it produced no packet and opened no gateway.

## Physical Result

Exactly one reviewed execution was attempted.

- Status: `stopped_safely`
- Completed frozen motion rows: `263 / 481`
- Completed hold rows: `0 / 80`
- Last persisted sample: index `262`, `t=6.575 s`
- Last persisted elbow request: `93.934066°`
- Last persisted elbow observation: `97.186813°`
- Elbow residual: `3.252747°`
- Consecutive no-progress samples: `40`
- No-progress duration: `0.975 s`
- Next planned sample: index `263`, `t=6.600 s`
- Stop mechanism: the next gateway result reached the one-second elbow
  stall-warning boundary and was rejected before persistence

All `263` persisted rows were precompiled, retained exact
requested/mapped/sent arrays, and reported zero route-row clamps, rate limits,
assistance, or intervention. The rejecting gateway result was not persisted,
so its returned joint arrays are unavailable and are not reconstructed.

Execution receipt:
`runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v2/stage-1/execution_receipt.json/execution_receipt.json`

Execution receipt SHA-256:
`296ddf95f1809b59b8fc784efeedcbe9fab0efde4d007a9b188f2abe2c978221`

Joint ledger SHA-256:
`0f6ff795ec316a285e76ec8b99da370211ba7dd23adbad5195ff9ba0642f8f6a`

## Camera And Scene Evidence

All three RGB lanes started before gateway motion and enclosed the persisted
interval.

- C922: `271` callbacks, `242` written frames, zero Apple drops, zero writer
  backpressure
- Native D405 RGB: exact bound device, `46` callbacks, `40` written frames,
  zero Apple drops, zero writer backpressure, `metric_depth:false`
- Pi IMX708: `740` frames

C922 start/end review shows unchanged board occupancy and no pawn or board
contact. Pi start/end review shows the arm remained high and contact-free.
D405 remained a ceiling-facing, action-enclosing supporting RGB lane without
task-outcome authority.

Visual review:
`runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v2/visual_scene_review.json`

Visual review SHA-256:
`fc695614b1437802fb4da90372a42bb8d4ee715ff235a34f292cc33b2834e4f2`

## Torque-Off Postflight

A fresh configuration-free read after cleanup confirmed torque disabled:

`[-6.681319, -92.395604, 101.670330, -50.417582, -104.131868, 1.662708]`

All joints are inside calibrated limits. The elbow is only `0.439560°` below
its upper limit and needs no clipping, but the recovery route did not complete
without a stall.

Postflight receipt:
`runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v2/postflight_torque_off_receipt.json`

Postflight SHA-256:
`781c4afd0956eeba8c3f917735a7c06c301640f3dbc20b7d2e7f2d589f064c56`

## Validation

- `uv run --locked pytest -q tests/test_wrist_view_reposition.py tests/test_pi_motion_video.py`
  - `30 passed`
- `scripts/audit_autonomous_workflow.sh`
  - clean
- Live process inventory after closeout
  - no gateway, native D405/C922 recorder, Pi recorder, or ffmpeg process

## Decision Boundary

Recovery v2 is terminal and cannot be retried or mutated. Although it produced
an in-range torque-off anchor, exact recovery tracking failed at the mandated
stall stop. No D1→D2 task action was frozen, no physical task motion occurred,
REAL→SIM physics was not run, and SIM→REAL remains forbidden.

Accepted proof class:
`physical_recovery_terminal_safe_stop_in_range_anchor_elbow_stall_no_task_or_transfer_authority`
