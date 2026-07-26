# Slice Brief 045 — Pi Distal-Tag Wrist Frame

## Required outcome

Determine whether physical tag 2 is rigidly attached before or after the
follower wrist-roll joint, using training-only model selection and one new
untouched heldout.

## Training-only body selection

Screen exactly two CAD bodies for tag 2:

- `left_wrist`, immediately before `left_wrist_roll`; and
- `left_gripper`, the body actuated by `left_wrist_roll`.

Use leave-one-pose-out tag-2 error across admitted training poses
A/B/C/E/F/I/J. Retain the Brief-044 training-only focal calibration and the
training-selected tag-1 body. No pose-L pixels may influence body selection or
parameter fitting.

## Frozen heldout L

Pose L is frozen before the wrist-body candidate is fit:

- target: `15, -78, 88, -95, 120, 3.0878859857482186`;
- role: heldout evaluation only;
- rationale: return pan/lift near the proven visible pose-F region while
  changing wrist roll by roughly 140 degrees from pose F;
- required observations: exactly one full-corner tag 1 and tag 2 detection.

Pose L must pass `8 px RMSE / 15 px maximum` across both tags with no joint
offset at its `±8 degree` bound. A passing diagnostic still cannot promote a
simulator parameter automatically. Stop before policy or task motion.
