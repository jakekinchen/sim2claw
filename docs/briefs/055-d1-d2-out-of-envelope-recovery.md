# Slice Brief 055 - d1 d2 out of envelope recovery

**Date:** 2026-07-27

**Status:** Terminal safe stop; recovery acceptance failed.

## Objective

Execute at most one independently reviewed, recovery-only route that takes the
fresh torque-off follower from elbow flex `104.483516°` to the previously
observed contact-free torque-off geometry consumed without clipping by
camera-pose setup v1, using a previously completed `90.614424°` inward elbow
preload, then prove the resulting torque-off pose is inside every calibrated
limit and consumable by the exact gateway without clipping.

## Product / Project Value

This removes the proven physical start-envelope blocker without contaminating
the prospective D1→D2 task action or its REAL→SIM identity claim.

## Acceptance Criteria

- Camera-pose setup v1 and wrist-dominant setup v2 remain byte-identical.
- Fresh follower identity and torque-off anchor match the reviewed route.
- The raw out-of-range elbow is admitted only as a recovery source state.
- The explicit setup clamp moves elbow only inward, by no more than `3°`, and
  is previewed at all nine frozen progress fractions for that one changed
  joint.
- The subsequent frozen float64 route first moves only elbow inward to the
  previously completed `90.614424°` recovery-clearance value, clearing the
  source-only model contact, then holds elbow there while moving the other
  five joints to the contact-free torque-off geometry consumed without
  clipping by camera-pose v1:
  `[-0.791209, -105.758242, 90.614424, -100.000000, -119.076923, 1.662708]`.
- The source-only contact admission is bound to the prior motion-free Pi view
  that shows a contact-free high arm. It permits only robot self-contact pairs
  present at the out-of-calibration model source, forbids worse penetration or
  new pairs, and requires every pair to clear before the route ends.
- CPU/fp64 preview reports no new or worsened kinematic contact and no
  external contact.
- C922, native D405 RGB, and Pi IMX708 start before setup motion and enclose
  the complete route.
- No pawn, board, table, or unrelated object contact is observed.
- No rate limit, clamp inside the counted frozen route, stall, assistance,
  intervention, IK, offset, or corrective suffix occurs.
- The executor closes torque off and a fresh configuration-free postflight
  reports every joint inside its calibrated interval without clipping.
- Recovery/setup bytes have no task, transfer, evaluator-promotion, or
  simulator-identity authority.

## Expected Files

- `configs/hardware/prospective_d1_d2_elbow_sag_recovery_tricam_v1.json`
- Ignored packet, review, camera media, joint ledger, and execution receipt
  under
  `runs/prospective-real-to-sim/20260727-d1-d2-elbow-sag-recovery-v1/`
- `docs/session-logs/037-executor-d1-d2-elbow-sag-recovery.md`
- `docs/reviewer-messages/035-d1-d2-elbow-sag-recovery.md`

## Test Plan

- Compile must fail closed on identity, anchor, snap, calibrated-limit,
  action-hash, or CPU/fp64 contact drift.
- Independent review must revalidate exact packet bytes and contact preview.
- Execution is single-use and stops on tracking, outward elbow motion,
  contact, stall, camera loss, or action modification.
- Focused recovery and tricam tests must pass.

## Validation Commands

- `uv run --locked sim2claw wrist-view-reposition --phase compile ...`
- `uv run --locked sim2claw wrist-view-reposition --phase review ...`
- `uv run --locked sim2claw wrist-view-reposition --phase execute ...`
- `uv run --locked pytest -q tests/test_wrist_view_reposition.py tests/test_pi_motion_video.py`
- `scripts/audit_autonomous_workflow.sh`

## Evidence To Record

- Fresh preflight anchor, limits, calibration hash, route/packet/action hashes.
- Setup-clamp delta and CPU/fp64 hyperrectangle receipt.
- Exact requested/sent/observed joint arrays and timing ledger.
- Camera identities, frames, drops, action enclosure, hashes, and cleanup.
- Final actual pose, residual, torque state, and fresh postflight margins.

## Reachability / Demo Proof

The repository previously completed the same recovery mechanism at:

`runs/geometric-microtransfer/20260727-geometric-sag-to-stable-anchor-recovery-tricam-v2/`

Its completed receipt is evidence for the mechanism, not authority to reuse
old action bytes or skip fresh review. The destination is bound separately to
the fresh torque-off, no-contact compile anchor in:

`runs/prospective-real-to-sim/20260727-d1-d2-camera-pose-setup-v1/packet.json`

Three earlier unfrozen candidate corridors for this brief were rejected
before packet creation because CPU/fp64 preview found either an inadmissible
folded self-contact or a transient path through the frozen envelope. Neither
rejection opened the gateway or commanded motion.

## Cross-Doc Impact

- Manager redirect:
  `docs/manager-log/003-d1-d2-recovery-redirect.md`
- Slice B remains inactive until the Slice A reviewer records `CONTINUE`.
- No headline Twin-fidelity or task-score change is allowed.

## Out Of Scope

- Pawn contact or task motion.
- Reproducing the old D1→D2 demonstration start.
- Metric D405 depth or camera calibration.
- New control frameworks, evaluator families, IK, offsets, task-action
  generation, simulator fitting, training, or Phase C.

## Stop Conditions

- Fresh anchor or hardware identity drift.
- Setup snap exceeds `3°` or moves elbow outward.
- CPU/fp64 preview reports new/worsened or external contact.
- Scene or cable geometry is unsafe.
- Any camera fails before motion.
- Any rate limit, unexpected clamp, action mismatch, tracking fault, stall, or
  contact occurs.
- Torque-off closeout cannot be independently verified.

## Outcome

One reviewed physical attempt stopped safely after 399/721 frozen motion
samples at the elbow one-second no-progress boundary. Torque-off, tricam
cleanup, and no pawn/board/table contact were verified. The fresh torque-off
elbow remained `1.846154°` above the calibrated maximum, so Slice A failed and
Slices B/C were not admitted. See session 037 and reviewer message 035.
