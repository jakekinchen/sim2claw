# Executor 035: anchored bidirectional transfer canary

## Current state

- Sole writer branch: `codex/anchored-transfer-20260727`.
- The prior writer is paused; latest handoff reported follower torque off.
- Fresh current-pose v2 completed as
  `prospective_diagnostic_bounds_satisfied_no_promotion` with zero fitting.
- The v2 physical packet used 57 exact float64 rows: the current-anchor-relative
  37-row shoulder-pan waveform plus a preregistered 20-row final hold.
- All 57 gateway samples were exact and healthy. The observed shoulder-pan
  excursion was `0.7032967 deg`; the final five samples were within the
  `0.5 deg` return tolerance.
- The C922, D405, and Pi IMX708 captures all enclosed the physical action
  interval and completed with `144`, `24`, and `230` frames respectively.
- A fresh follower-only read after replay reported
  `physical_follower_torque_enabled=false`, no configuration rewrite, and pose
  `[-8.3516484,-106.4615385,98.4175824,-100.1758242,-126.3736264,1.6627078]`
  in physical mixed units.
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
- Fresh v2 canary: prospective bidirectional diagnostic only; all frozen bounds
  passed, but neither transform nor evaluator is promoted.
- C8→A6 pawn sequence: not physically admissible; nine robustness failures and
  the unpromoted metric registration remain.

## Next executable step

No broader robot command is admitted. Use the new prospective canary receipt as
the timing/actuation diagnostic baseline, then continue metric camera and base
registration offline. A later physical action requires a separately compiled,
hash-frozen, independently reviewed packet and must not inherit authority from
this result.
