# Slice Brief 044 — Pi Focal-Calibrated Dual-Link Heldout

## Required outcome

Test whether an independently constrained IMX708 focal scale resolves the
two-link residual without reusing previously opened heldouts as fresh proof.

## Training-only camera family

Use the admitted tag observations from poses A/B/C/E/F/I/J only. Treat each
uniquely decoded 20 mm tag square as one calibration view. Fit one shared focal
length with:

- `fx = fy`;
- principal point fixed at `(768, 432)` for the 1536×864 image;
- zero tangential and radial distortion; and
- OpenCV intrinsic-guess calibration initialized from the official-FoV seed.

Then refit the two-link kinematic bundle with tag 1 on the training-selected
proximal body and tag 2 on `left_gripper`. No heldout pixels may influence
camera calibration, body selection, or parameter fitting.

## New frozen heldout

Pose K is frozen before the revised candidate is fit:

- target: `40, -55, 72, -95, 80, 3.0878859857482186`;
- role: heldout evaluation only;
- required observations: exactly one full-corner tag 1 and one full-corner
  tag 2 detection from the torque-on Pi still.

The capture may occur before fitting, but its image remains unopened by the
detector until the candidate file is frozen.

## Gates and evidence boundary

Pose K must pass at most `8 px RMSE` and `15 px maximum` across both tags, and
no fitted joint offset may reach its `±8 degree` bound. A passing diagnostic
still has no automatic simulator-promotion authority. The slice authorizes
static calibration motion only and stops before policy, teleoperation,
geometric task commands, or task motion.
