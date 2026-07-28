# Goal Loop — C922 Exact-Mode Calibration v1

## Mission

Build a deterministic, evaluator-owned path from public exact-mode C922 frame
bytes to independently scored camera intrinsics and lens distortion. Provide a
printable calibration target and fail closed when the required physical view
diversity is absent. Do not reuse the different-camera `IMG_5349` SfM or the
one-view zero-distortion visual fit as calibration evidence.

## Ordered Source of Truth

1. The owner’s request to advance the evaluator-owned Twin closure goal.
2. Clean baseline `d8046ca70270664c8be3e4747090a62d6f7b0180`.
3. The frozen S2 evidence and current six-domain Twin closure contract.
4. Verified C922 identity and exact `640 × 480`, `420v`,
   `30.00003000003 fps` AVFoundation mode.
5. `configs/evaluations/c922_exact_mode_calibration_v1.json`, the tracked
   target asset, and exact committed evaluator bytes.
6. Generated input frames and receipts, then GOAL, project state, ledger, and
   the terminal run log.

## Intended Outcome

The repository can consume a frozen 18-view-or-greater C922 checkerboard
dataset, detect every corner from image bytes, validate view diversity, fit
only the two preregistered camera models on the fit split, select on validation,
and score the selected model once on held-out views. A pass emits
metric-readiness-compatible intrinsics and distortion receipts. An unavailable
or inadequate dataset emits a sealed not-ready evaluation and no calibration
receipt.

## Acceptance Criteria

1. Preserve the frozen S2 eleven-file set and `1 event / 4 replays /
   0 measurement trials` byte-identically.
2. Commit this goal, target, and contract before evaluator implementation or
   any live camera access.
3. Bind the exact C922 device/model/mode/orientation and require one constant,
   explicitly recorded focus setting across the dataset.
4. The evaluator, not the input manifest, detects all `9 × 6` corners.
   Caller-supplied corners, duplicate frame bytes, path escapes, image-size
   substitution, device/mode substitution, and split overlap fail closed.
5. Require at least 18 accepted frames with frozen `12 / 3 / 3`
   fit/validation/held-out counts, five centroid bins, three scale bins,
   three orientation bins, at least four tilted views, and at least three
   near-frontal views.
6. Fit only the frozen zero-distortion and five-coefficient OpenCV models.
   Select on validation using the frozen `0.05 px` improvement rule. Do not
   expose held-out errors until selection is fixed.
7. Require fit, validation, and held-out RMS at or below `0.75 px`, held-out
   maximum error at or below `2.0 px`, bounded focal lengths/aspect ratio, and
   a central principal point.
8. Emit `camera_intrinsics_receipt.v1` and
   `lens_distortion_receipt.v1` only after every gate passes. Bind dataset,
   contract, evaluator, selected model, split counts, metrics, and source
   frame hashes.
9. The target’s `20 mm` squares and `200 × 140 mm` grid are nominal design
   values only. Metric extrinsics or board scale require a post-print direct
   measurement receipt; a calibration pass alone does not close geometry.
10. Add adversarial tests for leakage/substitution/replay, malformed images,
    caller corners, split mutation, insufficient diversity, model/threshold
    mutation, output replay, and fail-path receipt suppression.
11. This software transaction opens no camera, creates no new physical frame,
    moves no robot, runs no simulator, calls no provider, trains nothing, and
    changes no Twin-domain or task score.

## Evidence Standard

Report the exact commits and trees; contract, asset, evaluator, evaluation,
and any receipt hashes; accepted/rejected counts; diversity bins; model budget;
fit/validation/held-out metrics; adversarial and focused tests; frozen S2
proof; unavailable inputs; and closed authority.

## Decision Status

### Confirmed

- The retained 46-image/5,016-point calibration belongs to the portrait
  `IMG_5349` source camera at `1600 × 2844`, not the exact-mode C922.
- Existing C922 camera fits are explicitly one-view, visual-only, and
  zero-distortion or distortion-excluded.
- The current hash-bound 100 mm frame contains a partially occluded board and
  does not yield a complete `7 × 7` chessboard detection.
- Retained C922 recordings show only a few camera/workcell poses and lack a
  frozen calibration-target split and focus receipt.

### Assumptions

- A future operator can print the tracked target at 100 percent and present it
  in diverse poses. Actual printed dimensions may differ from nominal.

### Recommended Default

- Finish and test the offline evaluator first. Do not spend a live camera
  session until the target is physically present and the acquisition contract
  is separately frozen.

### Open Questions

- The actual printed target dimensions and measurement uncertainty.
- Whether the C922 autofocus setting can be read and locked by the future
  acquisition runner.

## Execution Rhythm

1. Commit the preregistration and target bytes.
2. Implement the pure evaluator and deterministic tests without camera access.
3. Obtain exact-byte review, run focused proof, and seal the pending-input
   result.
4. Open a separate physical acquisition only when target/focus preflight is
   available.

## Progress Ledger

```text
Current state: Preregistered; evaluator not yet implemented; no live session authorized.
Completed: Exact camera/mode binding, target design, split/diversity/model/acceptance rules.
Evidence: Baseline d8046ca; target 88419277; C922 unique ID 0x8310000046d085c.
Remaining: Implement/test/review evaluator, seal current pending-input result.
Blockers: No measured printed target or diverse exact-mode calibration corpus exists yet.
Next step: Implement the fail-closed public-input evaluator.
```
