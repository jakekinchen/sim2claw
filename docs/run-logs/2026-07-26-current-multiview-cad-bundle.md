# Current H/I/D multi-view CAD bundle

Date: 2026-07-26

Proof class: `physical_static_multiview_cad_and_fiducial_diagnostic`

## Outcome

The exact current SO-101 CAD, frozen scene board transform, frozen accepted
three-tag Pi model, and receipt-bound H/I/D captures were evaluated without
hardware access. H and I were the fit views. D was retained as a disclosed
retrospective holdout because a prior rejected four-tag refit had already
consumed it.

The primary result is a camera-state diagnosis, not a joint or tag-mount
promotion. The frozen Pi model began at:

- H: `47.4509 px` tag-corner RMSE;
- I: `44.0515 px`; and
- D: `51.0278 px`.

A six-DOF Pi-camera nuisance control fit on H/I changed the frozen camera by
the left-composed rotation vector
`[-0.006737, -0.016109, 0.252588] rad` and translation
`[-0.009009, -0.005345, -0.020393] m`. It reduced:

- H to `2.4308 px`;
- I to `4.9808 px`; and
- retrospective D to `12.9329 px`.

This is a `74.7%` D-RMSE reduction. It is full-rank in the bounded local
probe, but it is deliberately ineligible for promotion: the requested
parameter-family test froze the previously accepted Pi camera, and these
frames show that its state no longer describes the current images.

## Requested parameter families

No requested simulator family passed an honest heldout test:

| Family | Fit behavior | D Pi RMSE | Decision |
| --- | --- | ---: | --- |
| Joint zero | Three of five offsets hit the `±5 degree` bounds | `41.9564 px` | reject |
| Follower base pose | Rotation hit `-5 degrees`; translation hit `+30 mm` y bound | `37.9591 px` | reject |
| Tag mounts | tag 2 had only one fit view; multiple bounds hit | `38.8742 px` | reject |
| Pi camera nuisance control | coherent H/I improvement and best D result | `12.9329 px` | diagnostic only |

The C922 board fit enumerated all eight chessboard symmetries and used the
complete follower CAD edges to select
`[h8, a8, a1, h1]` with a `5.5331 px` margin. The board-conditioned solution
has a `1468.43 px` focal estimate, but its `9.0363 px` board-point RMSE is
slightly worse than the fixed-`1500 px` seed (`8.8850 px`). It is therefore
not current metric intrinsics/extrinsics. Exact-CAD trimmed edge RMSE is
`9.0070 px` on H, `12.8608 px` on I, and `17.8714 px` on D. D board-edge
median is `4.2426 px`, with a `26.9258 px` p90, reflecting occlusion and
uncalibrated lens distortion.

## Identifiability and next autonomous action

The added tags are useful, but their current view distribution matters:
tag 0 appears in both H and I; tag 2 appears only in H before D. Consequently,
tag 2's six-DOF mount is not independently identifiable in this split. The
strong camera-control result and the boundary-saturating joint/base/tag fits
identify current Pi camera extrinsics as the next software-only calibration
target. Refit one fixed Pi camera transform from the existing H/I observations,
then verify it against D and the prior N heldout before considering any tag,
base, or joint change. No new robot motion is required.

## Lineage and authority

- Contract: `configs/evaluations/current_multiview_cad_bundle_v1.json`
- Tool: `tools/evaluate_current_multiview_cad_bundle.py`
- Result:
  `runs/current-multiview-cad/20260726-v1/evaluation.json`

The result grants no C922 metric calibration, simulator-parameter promotion,
policy/task evidence, or physical authority. The follower was not accessed;
it remained reset and torque-off.
