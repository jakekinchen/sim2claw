# Slice Brief 048 — Current-Pi Three-Link Calibration

## Required outcome

Calibrate the current, physically changed Pi-camera view without mixing it
with the earlier camera extrinsic. Correct the follower fiducial map before
fitting lens or joint parameters.

## Acquisition

- Reuse the admitted zero-roll capture as a training observation.
- Acquire at least two diverse, previously admitted collision-free follower
  poses for training. A distinct pose may be added after a pose lacks one of
  the three tags; do not repeat the failed target.
- Freeze heldout pose M at
  `[-10, -72, 85, -95, 20, 3.0878859857482186] degrees` before compilation or
  capture. Its current-camera image must remain unopened until the
  training-side candidate family is frozen.
- Require one receipt-bound 1536×864 IMX708 still during a torque-on hold,
  exact joint samples, a clean camera close, and follower torque off.
- Detect tag IDs 0, 1, and 2 independently. Admit each unique visible
  follower-tag row; a pose need not contain all three tags because the shared
  camera and connected kinematics couple partial observations across poses.
  A missing tag does not authorize a repeat of the same target.

## Fit

- Compare physically adjacent body maps for tags 0 and 1 using training-only
  leave-one-pose-out scoring. Keep tag 2 on `left_wrist`.
- Fit one shared current-camera transform, connected joint zeros, and one
  rigid tag mount per selected body.
- Evaluate zero-distortion before any bounded radial-distortion family.
- Reject distortion coefficients at their bounds or a family that improves
  training while worsening heldout error.
- Render every original follower visual mesh, including the base, for visual
  diagnosis after the metric score is frozen.

## Gates

- Per-pose tag-corner RMSE at most 8 px.
- Per-pose tag-corner maximum at most 15 px.
- No joint-zero or distortion coefficient at its bound.
- One shared camera across training and heldout captures.
- No per-frame alignment or disconnected image-space part transform in the
  evaluation.

## Stop boundary

This slice authorizes reviewed follower-only static calibration captures. It
does not authorize policy execution, teleoperation, a physical task attempt,
or automatic simulator-parameter promotion.
