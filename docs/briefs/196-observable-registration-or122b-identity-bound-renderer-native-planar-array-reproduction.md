# OR122B: identity-bound renderer-native planar-array reproduction

OR122B binds a new implementation, test, contract, and output before its only
run. The exact five OR121 centerlines become `1,240` triangles in the shared
z-buffer, with endpoint reprojection error below `1.14e-13 px`. All integrity
gates and `3/3` focused tests pass before and after execution.

The result reproduces OR122's substantive terminal finding. All seven rows gain
outside-board edge F1 (`+0.017517` mean), but the local array ROI gain is only
`+0.053325` against `+0.10`, and full-frame similarity gains only `+0.000110`
against `+0.0004`. The board effect is exactly zero. Corroboration remains
unopened because development fails.

Visual inspection shows that the candidate contributes a small set of narrow
projected strokes while the physical-versus-simulator residual contains much
broader scene structure. Freeze a map-only failure attribution before adding
any more geometry. This is retrospective same-episode evidence, not semantic,
predictive, physics, transfer, or promotion authority.
