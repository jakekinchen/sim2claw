# Executor log 050: Q03 held-out label-authority correction

Date: 2026-07-27

Decision: the original Q03 held-out rejection is invalid; the held-out is
unscorable under its frozen camera-owned correspondence requirement.

## Defect reproduction

The original receipt is preserved unchanged at
`runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json`
with SHA-256
`7bfd06be5dd397a8c25dc7a4e3cdadd08fa006271fec38d4abcac27d04c125bf`.
Its `164.353128 mm` result is reproducible only by treating the old-simulator
route name `B7` as a physical square label.

That label is not camera-owned. The sealed C922 apex window shows the board,
but the high-hover pinch-to-pawn association is self-occluded by the arm and
wrist. The Pi apex frame shows the arm while the gripper is outside the right
image boundary. The D405 color stream points away from the board. The capture
declares no camera extrinsics, and the pinch is approximately `180 mm` above
the pawn plane, so a planar C922 pixel cannot be assigned to a board square
without a metric camera model.

Choosing a nearest square under v4 FK is forbidden because that would use the
model under validation to create its own held-out label. For transparency,
the closest model counterfactual with the frozen task-relative offset is A3
at `22.337386 mm`; the closest raw horizontal center is A2 at `19.719086 mm`.
Neither is a camera label or a valid held-out score.

## Corrected disposition

- fit residual: `24.631505 mm <= 25 mm`, pass;
- camera-owned physical square: unavailable;
- corrected held-out residual: unavailable;
- v4 metric admission: not supported;
- v4 metric rejection by held-out: not supported;
- F1 trigger: not supported;
- held-out open count: remains exactly `1`;
- new data or robot motion: none.

Proof class:
`zero_motion_single_open_heldout_label_authority_audit`.

The corrected receipt is
`runs/bidirectional-pawn-push/20260727-registration-v4-heldout-label-audit-v2/evaluation.json`.
It proves no physical, simulator, or transfer success.
