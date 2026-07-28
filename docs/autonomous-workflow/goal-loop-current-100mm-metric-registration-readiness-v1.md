# Goal Loop — Current 100 mm Metric Registration Readiness v1

## Mission

Turn the current-workcell geometry/scale gap into one evaluator-owned,
content-addressed readiness decision. Reuse the existing C922 C2→C1 recording
only as source evidence; do not infer metric scale, camera calibration, object
pose, or robot registration from pixels that do not contain those
measurements.

## Ordered Source of Truth

1. The owner's six-domain Twin-fidelity closure objective.
2. Exact clean baseline
   `17d297b2a58dcceec9c9e9449da84746978167dd`.
3. The terminal multilevel-HIL and isolated-host receipts and authority limits.
4. `configs/evaluations/pawn_transition_inference_readiness_v1.json`.
5. The immutable current-workcell C922 capture receipt, video, and extracted
   source frame named in the input manifest.
6. `configs/evaluations/current_100mm_metric_registration_readiness_v1.json`.
7. Exact committed evaluator/test identities.
8. `GOAL.md`, project state, orchestration ledger, and run logs.

## Intended Outcome

One deterministic receipt either declares that the frozen inputs are ready for
a separately owned metric board/object/camera fit, or emits a sealed
`measurement_prerequisites_missing` result listing every unavailable input.
Passing readiness is not a calibration result and does not change the
geometry/scale Twin-fidelity domain.

## Acceptance Criteria

1. Preserve all frozen S2, HIL, camera, lifecycle, and isolated-host evidence
   byte-identically.
2. Commit this goal, the contract, and the incomplete input manifest before
   implementing or running the evaluator.
3. Bind the existing C922 capture receipt, overhead video, and source frame by
   path and SHA-256. Verify that the capture receipt independently binds the
   video, exact camera identity, image size, orientation filter, proof class,
   and closed promotion/training authority.
4. Treat the extracted frame as available pixels only until a deterministic
   extraction receipt binds its source video, timestamp, decoder identity,
   orientation, and frame digest.
5. Require a directly measured board playing side with uncertainty and
   measurement-tool identity. A nominal chessboard size, historical photo
   registration, AprilTag print setting, or simulator dimension is not a
   physical measurement.
6. Require hash-bound camera intrinsics and lens-distortion calibration for
   the exact C922 capture mode.
7. Require at least eight spatially distributed board correspondences, all
   four board quadrants, two independent annotations per point, and an
   evaluator-owned held-out or leave-one-out board-plane RMS no greater than
   `0.0015 m`.
8. Require metric object base-center/keypoint observations with uncertainty
   and a hash-bound overhead-camera-to-robot/workcell transform. Keep wrist
   extrinsics as a separately named missing input when unavailable.
9. Do not accept self-scored thresholds, mutable result fields, proposal-only
   homographies, bounding-box centers, unverifiable paths/hashes, or synthetic
   fixture values as physical measurements.
10. Add adversarial tests for source drift, receipt substitution, nominal
    scale substitution, missing distortion, insufficient points/annotators/
    quadrants, self-scoring, malformed uncertainty, and replayed output roots.
11. Execute the evaluator exactly once on the frozen incomplete manifest.
    Generate no camera session, frame, robot motion, simulator replay,
    provider call, training row, promotion, or physical/task claim.
12. Seal exact hashes, missing prerequisites, budgets, proof class, and
    authority. A future acquisition or fit must use a new versioned
    transaction rather than editing this result.

## Evidence Standard

Report exact commits/trees; goal, contract, input-manifest, evaluator, source
receipt/video/frame, result, and receipt hashes; source camera and capture
identity; each readiness gate; the ordered missing-prerequisite list; zero
capture/motion/simulator/provider accounting; focused tests; frozen-evidence
proof; and closed authority.

## Decision Status

### Confirmed

- The closure matrix remains `0 / 6`; geometry/scale is `missing`.
- The current C922 C2→C1 recording is a real physical observation with a
  content-addressed video and capture receipt.
- The recording is diagnostic RGB only. Its receipt does not provide metric
  depth, camera intrinsics/distortion, board scale, object keypoints, camera
  extrinsics, or evaluator-owned consequence.
- Existing historical/proposal homographies are explicitly visual-only or
  unreviewed and cannot supply current metric authority.
- The one reviewed evaluator execution verified the existing source lineage
  and returned `measurement_prerequisites_missing` with ten missing gates and
  zero invalid inputs.

### Assumptions

- None of the missing metric inputs may be reconstructed from file names,
  nominal product dimensions, simulator constants, or earlier visual fits.

### Recommended Default

- Seal the current manifest as measurement-incomplete. Use the resulting
  packet to drive one later acquisition that measures the board, calibrates
  the exact camera mode, and records independent distributed annotations.

### Open Questions

- Which traceable physical measurement tool will measure board scale and its
  uncertainty.
- Whether the exact C922 mode can be calibrated in place or needs a separate
  calibration-target session.
- How the overhead camera will be registered to the robot/workcell frame after
  its isolated-host attachment.

## Execution Rhythm

1. Commit this preregistration, contract, and incomplete manifest.
2. Implement the pure evaluator and adversarial tests without hardware access.
3. Commit exact evaluator bytes and obtain a narrow pre-execution review.
4. Execute once on the frozen manifest, seal the result, and update durable
   project truth.
5. Stop before any new capture or metric fit.

## Progress Ledger

```text
Current state: Terminal measurement-prerequisites-missing result; one readiness-evaluation budget exhausted.
Completed: Preregistration 86e7c85; final reviewed evaluator 4bdba09; 1/1 offline readiness evaluation; tracked exhaustion control.
Evidence: Source receipt 3fafb113 / video 1643520f / frame 2543230b; evaluation 5900ff12 / digest bb7bd2f3; receipt file 12b1624d / digest 18bcbb02.
Remaining: New versioned acquisition for the ten named metric measurements; no v1 retry.
Blockers: Direct board measurement, extraction receipt, exact-mode intrinsics/distortion, independent annotations, object keypoints, and camera/workcell extrinsics are unavailable.
Next step: Measure and calibrate under a new preregistered transaction after the fixed C922 attachment is established; do not rerun v1.
```
