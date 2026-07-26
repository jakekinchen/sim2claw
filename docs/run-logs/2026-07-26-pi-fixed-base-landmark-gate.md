# Pi fixed-base explicit-landmark gate

## Outcome

The two proposed fixed-base correspondences are **not defensible exact
3D-to-2D landmarks in the existing H, I, F, and fresh N images**. The gate
therefore stopped before optimization.

No physical pixel was accepted as a landmark, no shared-camera adjustment
was fit, and no joint, tag mount, mesh, or simulator parameter changed.
Before/after metrics and Pareto improvement are intentionally not reported
because there is no valid correspondence set to optimize.

## Feature 1: upper-left outer motor-housing corner

The relevant visual is `left_base_so101_v2`, but the physical image boundary
is a broad printed fillet rather than a point corner. The frozen-camera
projection's upper-left support representative is mesh vertex `3238`:

- local XYZ:
  `[0.0189142656, -0.0596297160, -0.0123932511]` m
- frozen projection: `[611.7053, 383.7859]` px
- other mesh vertices within 2 px of that projection: 30

Selecting vertex `3238` would therefore choose one tessellation sample among
31 visually equivalent samples on a curved surface. In the physical images,
the candidate region `[495, 400, 555, 465]` contains no repeatable sharp
corner to select. It was retained as an ambiguity region, not labeled as a
point.

## Feature 2: upper-right housing-to-column corner

The proposed image feature is a T-junction formed by the fixed housing,
motor/mounting-plate edges, and the shoulder/column that occludes them
differently by pose. It is not the projection of one fixed `left_base`
surface point.

The arbitrary `left_base_so101_v2` right-support representative is vertex
`1631`:

- local XYZ:
  `[0.0304295216, 0.0414505526, -0.0305334069]` m
- frozen projection: `[797.2332, 454.7067]` px
- other mesh vertices within 2 px of that projection: 45

The physical candidate region `[675, 390, 765, 475]` changes its visible
intersection as the shoulder pose changes. It too was retained only as an
ambiguity region.

## Decision

`accepted_correspondences` is empty. Fitting six camera degrees of freedom
from arbitrary points would let the optimizer trade tag accuracy against
annotation choice, not measure fixed-base registration. Consequently:

- shared camera fit performed: false
- per-frame fit performed: false
- tag residuals changed: false
- landmark residuals computed: false
- Pareto improvement evaluated: false
- simulator-promotion authority: false

The minimal prospective alternative is two high-contrast point fiducials
rigidly attached to `left_base`, with their 3D coordinates surveyed in the
base frame. Those would provide genuine point correspondences without
relying on a fillet or an occlusion junction.

## Local evidence

- gate receipt:
  `runs/pi-link-tag-calibration/20260726-fixed-base-landmark-gate-v1/receipt.json`
  (`e75dbaeb347113242c56a3c5dd73ce1f7f22d0848b6968d705200155711e2dce`)
- four-frame ambiguity visualization:
  `runs/pi-link-tag-calibration/20260726-fixed-base-landmark-gate-v1/visualization.jpg`
  (`04246872488033389edaa9b0f7f4f7ca0dffa9c00e63758dbc688b8c97413be4`)

All evidence is diagnostic-only. No hardware ran.
