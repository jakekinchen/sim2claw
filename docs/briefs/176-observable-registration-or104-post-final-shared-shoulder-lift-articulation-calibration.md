# OR104 — Post-final shared shoulder-lift articulation calibration

## Question

Can one renderer-only shoulder-lift gain/offset pair, shared by both robots and
all episodes, materially improve the robot-dominated outside-board edge match
without changing replay actions, state, dynamics, timing, contact, camera, or
static workcell geometry?

## Frozen method

- Bind the OR95 eleven-episode action-identical renderer and OR103's trace-only
  selection of `shoulder_lift`.
- Sample the 25%, 50%, and 75% OR95 evaluation rows in every episode using the
  contract's exact integer rule.
- Estimate one deterministic hinge-axis basis per side from development traces
  alone. This defines coordinates; it does not select a pixel-scored parameter.
- Search the Cartesian product of five excursion gains and five offsets using
  all 21 development samples and the exact full-mesh renderer.
- Include `(1.0, 0 degrees)` as the identity baseline and verify its metrics
  reproduce the corresponding OR95 frame rows to numerical precision.
- Freeze one global pair before opening the four already-seen validation
  episodes. Validation cannot select, refit, retry, or change thresholds.

## Acceptance and limits

Development requires a mean outside-board edge-F1 gain of at least `0.02`, with
at least 14/21 samples gaining `0.01`. If that passes, validation requires a
mean gain of `0.015`, with at least 8/12 samples gaining `0.01`. Mean board-edge
and full-frame similarity regressions are each bounded at `-0.01`.

This is retrospective sampled calibration, not an untouched-cohort result, a
physics or kinematic-fidelity proof, physical transfer, or simulator promotion.
No pixel warp/composite, simulator replay, action/state mutation, hardware, or
paid compute is allowed.
