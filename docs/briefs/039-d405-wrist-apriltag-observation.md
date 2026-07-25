# Brief 039: D405 wrist AprilTag observation

Date: 2026-07-25

## Goal

Create the smallest truthful camera-only path for observing the existing scene
AprilTag through the D405 wrist RGB stream, without waiting for the C922
checkerboard calibration lane.

## Boundary

- Reuse the pinned OpenCV AprilTag implementation already in the project.
- Bind an existing native D405 video to its common-session recorder report when
  that report is available.
- Detect the repository-identified `tag36h11` ID `0` and retain pixel corners.
- Keep the source design's 80 mm black-border side explicitly nominal.
- Do not open a camera, construct a robot gateway, move hardware, solve metric
  scale, infer depth, or establish wrist/workcell extrinsics.

## Acceptance

The CLI writes a source-hash-bound receipt for positive and negative
observations, rejects mismatched native recorder lineage, and enumerates the
physical measurements and transforms still required for wrist registration.
Focused tests cover a synthetic positive, a truthful negative, exact native
video binding, and a mismatched-source rejection.
