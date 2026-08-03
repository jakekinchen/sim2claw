# OR56 — Static renderer appearance factorization

Decision: `CONTINUE`

Evidence anchor: `OR55`

OR55 establishes a `0.703623` full-frame mean, `0.670299` motion-region mean,
and `0.226697` tolerant-edge F1. All phases miss. Before changing physics or
geometry, measure how much of the gap a single time-invariant renderer camera
response can explain on untouched temporal blocks.

## Required outcome

Freeze development, validation, and stress sample ranges before fitting. Fit a
bounded family of global BGR affine camera-response transforms on development
pixels only, pair them with a small fixed Gaussian-blur family, and select only
by development score. Report the untouched validation and stress scores for
the selected candidate alongside the unchanged baseline.

## Frozen constraints

- Bind the OR55 contract, closeout, receipt, per-frame rows, and immutable OR26
  physical/simulator videos by SHA-256.
- Use exactly one transform for the whole video; no frame-, phase-, object-, or
  region-specific correction is allowed.
- Fit only camera response and fixed blur. No geometric warp, simulator rerun,
  state change, action change, physical-pixel compositing, physical imagery as
  a texture, segmentation-derived replacement, or background plate is allowed.
- Select on development data only. Validation and stress blocks remain sealed
  until selection is frozen.
- This is a permanently episode-specific, outcome-informed visual diagnostic.

## Terminal rule

Emit the selected candidate video and score it with the unchanged OR55 metric.
If a time-invariant response explains less than `0.02` absolute validation
similarity without regression on stress, reject photometric response as the
next main mechanism and advance to renderer scene composition/geometry. A
target pass still proves only episode-specific visual replay, never physics or
transfer.
