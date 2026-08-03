# OR101 — post-final robot dynamic-footprint scale attribution

## Decision

Measure the projected robot-motion footprint mismatch from immutable OR97 occupancy maps before fitting another transform.

## Method

- Read the eleven hash-bound four-panel OR97 occupancy PNGs.
- Use only the already-derived physical and candidate dynamic panels.
- Measure occupied pixels, bounding boxes, diagonals, and centroids; verify panel counts against the OR97 receipt.
- Select independent camera-ray robot-depth registration before articulation only if the median physical/candidate area ratio is at least `1.5`, at least `9/11` episodes meet that ratio, and the median bounding-box diagonal ratio is at least `1.2`.
- Otherwise select articulation residual work only when mean OR97 dynamic F1 remains below `0.6`.

## Boundaries

JSON-only. No physical video decode, render, fit, transform value, replay, hardware, paid compute, same-video claim, kinematic or physics claim, transfer, or promotion.
