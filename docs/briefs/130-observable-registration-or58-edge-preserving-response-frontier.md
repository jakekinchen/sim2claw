# OR58 — Edge-preserving global-response frontier

Decision: `CONTINUE_RETAINED_VIDEO_ONLY`

Evidence anchor: `OR56`; runtime boundary: `OR57`

OR56 reaches `0.793053` mean similarity but loses edge F1 under blur. OR57
cannot render on any available local lane. Use immutable videos to determine
whether one global response can clear the requested pixel range without
collapsing the frozen edge check.

## Required outcome

Evaluate a preregistered `5×5×4` grid of common-channel gain, bias, and blur
values on development frames. If any candidate reaches development mean
`>=0.80`, select the one with the best edge F1, then p10. Open validation and
stress only after selection, emit one small video, run every OR55 gate, and
emit an `8×6` spatial residual table.

## Frozen constraints

- Bind OR55–OR57 receipts/closeouts and the immutable OR26 physical/simulator
  videos.
- Use one response for the complete timeline. No renderer, warp, per-frame,
  phase, region, or object correction is allowed.
- No physical pixel may be composited, copied as a texture/background plate,
  or used for anything except development scoring and the sealed evaluator.
- Missing frames remain excluded and unfilled.
- Do not install dependencies or start Colima while host free space remains
  below `1 GiB`.

## Terminal rule

Only all five unchanged OR55 gates establish the full temporal-pixel target.
A mean/p10 result in the requested range with a failed edge gate is recorded
as partial numeric pixel similarity, not the same simulated video and not
physics fidelity.
