# Executor log 089 — Observable registration OR1

Date: `2026-07-29`

## Outcome

OR1 accepts a bounded C922 camera/world projection and rejects exact intrinsic
calibration. The prior unconstrained 3x4 projective camera fails physical
plausibility with `191.571 px` skew and `1.858` focal aspect ratio. It had
absorbed non-camera error.

The prospectively frozen square-pixel, centered, zero-distortion-assumption
family uses only 25 board-lattice points. It passes all bounded gates at
`2.270 px` RMS and `5.652 px` maximum reprojection, with a proper rotation,
positive depth, full-rank seven-parameter Jacobian, and no active focal bound.
It consumes zero robot, jaw, pawn, contact, or outcome rows.

## Evidence

- freeze commit: `8a75aa1`;
- receipt SHA-256:
  `a2fda1032ad70c026fb8e82f3849896926ee92f07a14f5ecdf8e827141324614`;
- artifact SHA-256:
  `f6add6ce80386e9795d2f51e65d42dfad042ebf095b3a1b325aa253c2d4baeb4`;
- focal: `1178.374 px`;
- horizontal/vertical FOV: `30.386 / 23.024 deg`.

## Validation

- `uv run pytest tests/test_observable_camera_world.py -q` — `3 passed`;
- authoritative receipt rebuilt byte-identically;
- all frozen bounded-model gates passed.

## Boundary

The model fixes the principal point, square-pixel ratio, and zero distortion.
Those are assumptions, not measured exact-mode calibration. Existing
known-outcome validation is not reused for promotion. OR1 does not approve
robot, jaw, floor, support, contact, or transfer mapping.
