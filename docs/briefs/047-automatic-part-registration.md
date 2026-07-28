# Slice Brief 047 — Automatic Part Registration

## Required outcome

Replace visual guessing with a bounded optimize/measure/verify loop that can
nudge each projected follower part, report the required adjustment, and test
whether those adjustments are explainable by one shared 3D camera and
kinematic model.

## Fit evidence

- Use the exact candidate-manifest visual meshes and receipt-bound encoder
  states.
- Use uniquely decoded follower tags 1 and 2 as high-weight correspondences.
- Use physical-image edges only inside visibility-aware neighborhoods of the
  projected follower.
- Exclude collision proxies, the crossing arm's tag 0, background edges, and
  out-of-frame geometry.
- Keep local part adjustments diagnostic until a shared 3D parameterization
  reproduces them across multiple poses.

## Verification

- Report before/after tag-corner and part-edge residuals separately.
- Freeze fit poses before optimization and score at least two non-fit poses
  without per-frame adjustment.
- Reject any candidate that improves the fit frame but worsens the aggregate
  non-fit score or requires disconnected part transforms.
- Preserve the original image, unadjusted projection, adjusted diagnostic, and
  machine-readable receipt.

## Stop boundary

This slice may use existing static images, simulation, and reviewed
follower-only static calibration captures explicitly authorized by the owner.
It performs no policy execution, teleoperation, physical task attempt, or
simulator-parameter promotion.
