# D405 chessboard-surface plane admission v1

Date: 2026-07-25

Proof class:
`physical_calibration_setup_chessboard_surface_plane_observations_only`

This prospective synchronized-capture path replaces the wall-oriented
all-valid-pixel fraction gate with a preregistered absolute support gate:
at least 12,000 fitted plane pixels in a frame. Each frame must also pass
metric residual and camera-distance limits. A deterministic pairwise-stable
subset is selected using normal-angle and plane-offset gates; individual
transients are retained in `rejected_observations` with exact rejection
reasons instead of aborting the capture.

At least three stable accepted frames are required. Fewer frames produce a
stored, rejected capture receipt. The stationary-wall
`d405_metric_surface_plane_v1.json` contract was not changed.

The existing raw capture
`runs/d405-pose-plane-capture/20260725-recovered-elbow90-v2` remains rejected
and was not retrospectively evaluated or promoted. Its raw database SHA-256 is
`127b35c16cff382a54f84e66266d08b9f5c674190731b53a275d0246b88c2b24`;
its route receipt SHA-256 is
`ef3c26dc6ef5dabaaf596a0e5132e54a8e271a589f6859d0673ab86fbdb5bf7b`.

All authority remains false. This evaluator does not establish board origin,
camera-to-robot extrinsics, physical safety, policy success, or task success.
No camera or robot was accessed during implementation or testing.
