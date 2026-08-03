# OR66 — Pixel-free static environment curve and finite-shape expansion

Decision: `DEVELOPMENT_FREEZE_THEN_NO_SELECTION_HELDOUT_EVALUATION`

Evidence anchor: `OR65`

OR65 leaves non-motion outside-board context as the dominant residual after
all 24 OR63 lines. Extract a second, bounded vector family that represents
curved and finite static contours which the line family cannot express.

## Required outcome

Using development frames only, recompute the frozen physical-only persistent
outside-board residual, remove a fixed neighborhood around the OR63 line
skeleton, find deterministic connected contours, simplify them to closed
polylines, and retain at most `32` primitives and `512` total vertices. Freeze
the JSON scene specification before scoring validation and stress. Union the
full new family with the OR64 line counterfactual and report edge F1 for every
partition and all `516` frames without family-size selection.

## Frozen constraints

- Keep OR55 Canny thresholds, OR26 board polygon, OR63 lines, and OR64 metric
  behavior unchanged.
- Use development occurrence thresholds `physical >= 0.35` and
  `simulator <= 0.10`; a `7 px` line-neighborhood exclusion; `5 px`
  morphological closing; contour perimeter `>=20 px`; bounding extent
  `>=8 px`; and simplification epsilon `max(1.5 px, 1.5% perimeter)`.
- Rank by development contour perimeter and take the first family within the
  fixed primitive/vertex budgets. Validation and stress cannot select or edit
  it.
- Emit JSON vectors and metric rows only. No mask, BGR pixel, image, texture,
  video, physical background, render, scene mutation, warp, or action/state
  change.

## Terminal rule

Untouched validation must improve at least `0.02` over the exact OR64 24-line
counterfactual to advance the family. Crossing `0.40` remains headroom only;
this card cannot pass the same-video target without a decoded simulator video.
