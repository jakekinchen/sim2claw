# D405 stationary metric surface-plane diagnostic

Date: 2026-07-25

Proof class:
`physical_stationary_metric_surface_plane_observation_only`

Verdict: `physical_stationary_metric_surface_plane_observed`

## Scope

This diagnostic consumed only the accepted stationary RGBD receipt, its two
extracted metric depth CSVs, its two extracted RGB PNGs, and the enumerated
848x480 Z16 depth intrinsics preserved by that receipt. It did not access a
camera or robot.

The result is one dominant visible metric surface plane in the D405 camera
frame. It is not a semantic board-plane claim. It does not establish the full
playing grid, a board origin, a camera-to-robot extrinsic, robot or board
height, task success, policy performance, or motion authority.

## Method and fail-closed gates

The evaluator:

1. Requires the accepted
   `physical_stationary_rgbd_capture_only` receipt and its passing verdict.
2. Verifies every consumed CSV and PNG against the accepted receipt's artifact
   hash inventory.
3. Requires the enumerated 848x480 Brown-Conrady depth intrinsics with all-zero
   distortion coefficients before pinhole deprojection.
4. Fits each frame with deterministic seeded RANSAC, then iterated
   total-least-squares refinement.
5. Requires at least 75% valid depth, at least 55% dominant-plane inliers among
   valid pixels, RMS <=0.5 mm, p95 absolute residual <=0.8 mm, cross-frame
   normal drift <=0.5 degrees, plane-offset drift <=1 mm, and optical-origin
   plane distance between 50 and 200 mm.
6. Reuses `d405_board_grid_visibility_v1` on each RGB PNG and requires the
   existing partial-grid classification. This plane diagnostic never promotes
   that partial view into full-grid registration.

Lineage mismatch raises a fail-closed evaluation error. Measurement threshold
failures produce a negative receipt with named failed checks.

## Command

```bash
.venv/bin/python scripts/evaluate_d405_metric_surface_plane.py \
  runs/d405-rgbd-capture/20260725-stationary-v2 \
  --output \
  runs/d405-rgbd-capture/20260725-stationary-v2/evaluation/surface-plane-receipt.json
```

## Metric results

| Metric | Frame 60 | Frame 61 |
| --- | ---: | ---: |
| Valid depth fraction | 0.805886399 | 0.800081073 |
| Plane inlier fraction of valid | 0.600598120 | 0.600184238 |
| Plane centroid camera XYZ (m) | `[0.0204365, -0.0219342, 0.0939286]` | `[0.0214051, -0.0220212, 0.0941060]` |
| Plane normal camera XYZ | `[-0.185731, 0.174934, 0.966903]` | `[-0.185932, 0.173334, 0.967153]` |
| Optical-origin perpendicular distance (m) | 0.083187168 | 0.083217992 |
| RMS residual (m) | 0.000315329 | 0.000318810 |
| p95 absolute residual (m) | 0.000626361 | 0.000642931 |
| Inlier camera-Z p01/median/p99 (m) | 0.0775 / 0.0929 / 0.1162 | 0.0775 / 0.0931 / 0.1169 |

Cross-frame normal angle is 0.093487138 degrees. Plane-offset drift is
0.0000308244 m.

## RGB partial-grid preservation

- Frame 60: 3 directly supported row lines and 2 column lines.
- Frame 61: 3 directly supported row lines and 1 column line.
- Both observations remain
  `partial_grid_visibility_not_outer_quadrilateral`.
- All four outer-boundary records require extrapolation.
- `full_grid_registration=false`.

## Receipt lineage

- Accepted capture receipt:
  `aa9eeb5081977c13c88763b6e1f93c1d1dbed459dd20da4de03084ec60a8070a`
- Metric-plane contract:
  `1d04adb5e2d91f0019c485792538ef6baf048a8573939e7a4e9c8dce33a6baed`
- Depth frame 60 CSV:
  `814d7a8870d9b57238ba67350f79f8f2f711d8d1007d7363b7630b6cbe1cecd4`
- Depth frame 61 CSV:
  `3f1739bbbc1a9f2fee1180dc9e5ef19c29598191eea254df288e07c98cb2f0d2`
- RGB frame 60 PNG:
  `34544cc3cac3f79db27dcb7f608845cc780c48f5dfa3e1bb5d9ffe11752b39ce`
- RGB frame 61 PNG:
  `15fb74ce955cd857df0e9f1086bea6838f7d3e59281b22588de7f496091d6757`
- Generated ignored surface-plane receipt:
  `0561d0eb7cb7e6b93c9ccb7fa629c6487f8b47c65c63274d588b1644e7eb8d13`

## Focused verification

```text
.venv/bin/pytest -q tests/test_d405_metric_surface_plane.py
....                                                                     [100%]
4 passed in 0.50s
```

The tests cover robust recovery from a synthetic plane with 25% outliers,
existing-artifact integration, fail-closed consumed-artifact hash mismatch,
and a forced negative verdict when the cross-frame stability threshold is
tightened below the observation.
