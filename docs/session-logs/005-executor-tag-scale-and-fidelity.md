# Executor Session 005: Tag Scale and Fidelity

## Scope

Started the approved hardware-free fidelity campaign. Audited the exact
IMG_5349 video, global-SfM frame, real 3DGS release, visible AprilTag design,
camera intrinsics, board-scale hypotheses, and the existing action-frozen
evidence.

## Implementation

- Added a fail-closed metric-scale plausibility contract.
- Added source-bound AprilTag detection, reviewed Hough-grid line fitting,
  nominal-tag PnP, parallel-plane sensitivity, candidate comparison, overlay,
  and receipt generation.
- Bound source video, frame, and real-splat SHA-256 values.
- Kept every physical/calibration/promotion authority flag false.
- Rewrote the live hardware-free plan to v1.1 with the action-invariance,
  composite-freeze, vector-evaluation, and gated-training amendments.

## Verification so far

- `uv run --offline pytest -q tests/test_pawn_scene_metric_scale.py`
- Result: 3 passed.
- Live receipt decision: 355.6 mm nominal-print consistent; 301.3 mm materially
  inconsistent; physical metric scale not established; promotion disallowed.

Additional executed pipelines:

- training-only endpoint appearance intervals: 11/11 source-loss and 11/11
  destination-return events, with explicit abstention from contact or metric
  object trajectory;
- timestamp/application ablation: 110 ms selected; 2.563 to 1.461 degrees
  joint RMS and 20.843 to 16.417 mm EE RMS;
- reset/reference audit: first commanded improves only 0.002% over first
  measured; below materiality and not the primary gap;
- lift/elbow deadband: 2 degrees selected in all four folds; 1.296 degrees
  joint RMS, 12.936 mm EE RMS, 69.6%/58.9% flat-response reproduction;
- unchanged-action consequence: 11/11 contact, 2/11 lift, 0/11 strict success;
- frozen rubber-tip ensemble: 2--3 lifts, 0 strict successes, no parameter
  selection; and
- composite publication receipt: deterministic 10,000-replicate
  whole-episode bootstrap, evidence hashes, regeneration commands, figure, and
  fail-closed terminal-negative verdict.

Final focused verification:

```text
uv run --offline pytest -q tests/test_pawn_scene_metric_scale.py tests/test_pawn_bg_endpoint_motion.py tests/test_pawn_bg_timing_ablation.py tests/test_pawn_bg_servo_deadband.py tests/test_pawn_bg_reset_reference.py tests/test_pawn_bg_contact_sensitivity.py tests/test_pawn_bg_publication_gate.py
```

Result: 18 passed in 309.08 seconds. `python -m compileall` and
`git diff --check` also pass.

## Current proof state

Accepted conditional physical-plausibility evidence plus cross-validated
timing and actuator-model diagnostics. The hardware-free campaign is complete
at the retained-data boundary. Physical accuracy, composite simulator
promotion, training admission, policy promotion, and transfer remain false.

Proof-state reconciliation: the earlier fixed-data event pipeline already ran
an evaluator-owned decode over all three split-held-out videos. They may be
used only as already-opened regression evidence. There is no remaining fresh
physical-video admission cohort.
