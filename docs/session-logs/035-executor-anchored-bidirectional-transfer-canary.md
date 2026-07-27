# Executor 035: anchored bidirectional transfer canary

## Current state

- Sole writer branch: `codex/anchored-transfer-20260727`.
- The prior writer is paused; latest handoff reported follower torque off.
- Historical execution-v4 now materializes as
  `retrospective_metrics_within_bounds_no_promotion` while preserving candidate
  config canonical SHA
  `fbf451821e96c9f236b89feb076b964fd81f52416028f93e627118e296697368`.
- Historical reverse diagnostic:
  - shoulder-pan RMSE: about `0.2621 deg`;
  - shoulder-pan maximum absolute error: about `0.5156 deg`;
  - measured pan peak-to-peak: about `1.1429 deg`;
  - simulated pan peak-to-peak: about `2.0306 deg`.
- The Pi IMX708 motion sidecar completed a camera-only 8-second smoke capture:
  230 frames at 1536×864, with matching PTS/container counts.
- IMG_5431 observation manifest sampled 108 frames and detected IDs 0–6 with
  counts `25,14,19,7,12,2,8`. Integer ID 0 is physically duplicated, so no
  cross-frame instance or 3D-point identity is inferred.

## Evidence classifications

- IMG_5431: hash-bound physical-video pixel observations only.
- New teleop/ROM recordings: physical source diagnostics, not exact replay.
- Historical canary reverse replay: retrospective replay diagnostic only.
- Fresh canary, if completed: prospective bidirectional diagnostic only.
- C8→A6 pawn sequence: not physically admissible; nine robustness failures and
  the unpromoted metric registration remain.

## Next executable step

Commit the implementation and evaluator freeze. Then compile a fresh
current-pose normalization plan, execute normalization only if required,
compile and independently review the new prebound canary packet, run the
tri-camera exact canary, replay it, and leave the follower torque off.
