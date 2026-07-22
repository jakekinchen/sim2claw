# 2026-07-22 C2 grasp-retention resolution

## Outcome

The action-frozen simulator campaign closed terminal-negative after 98 C2
candidate replays and zero anchor passes. Fixed-pad alignment, finite force,
contact dimensionality, rigid-contact compliance, manufacturer-scaled current,
load-hold actuator hysteresis, calibrated loaded aperture, composite geometry,
and rounded capsule pads were tested in source-bound families.

The simulator is not promoted. The experimental load-hold transfer remains
disabled unless explicitly selected by a diagnostic contract. Reopening
requires direct jaw-force and rubber-cap deformation measurements.

## Verification

- Campaign/action invariance: 98/98 candidates used C2 action SHA-256
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`.
- Targeted tests: `21 passed`.
- Full repository: `805 passed, 3 skipped, 328 subtests passed` in 1306.60 s.
- Closeout receipt digest:
  `3887636e0a04b09289337e09a06c82867fcd6beb13b46b27fcfed8e6f73d2f14`.

## Resource closeout

The campaign used local CPU simulation only. It created no Brev resource and
no Docker container; `docker ps` was empty at closeout. No task-created pytest
or MuJoCo process remained after the full suite. Pre-existing read-only Studio
and Playwright processes were left unchanged.
