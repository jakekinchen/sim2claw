# Brief 087 — Realized-Action C4 Effective Plant

Decision: `CONTINUE`

Evidence anchor: `106`

## Active card

C4 from the realized-action outcome calibration queue.

## Required slice

Fit one bounded effective SO-101 plant using fit episodes only:

- preserve requested and gateway-sent bytes;
- model the already-observed gateway transform only by retaining the sent lane;
- compare direct target, the existing diagnostic `0.11 s` ZOH path, and a
  three-sample command-hold challenger;
- after the frozen hold, fit bounded per-joint response and only the
  cross-episode direction-conditioned residual admitted by C3A;
- initialize from the episode's first measured robot state;
- emit requested, sent, applied, measured, and timestamp traces separately;
- evaluate once on validation, then report the sealed episode without using it
  for selection.

## Verification gate

- Requested and sent source tensor hashes remain byte-exact.
- No clipping, smoothing of evidence actions, retiming of source timestamps,
  IK repair, offsets to source actions, or observed-state driving after
  initialization occurs.
- The identified plant improves pooled validation joint and provisional EE RMS
  by frozen margins versus direct target.
- No material per-joint validation regression is allowed.
- Sample hold remains a sample-domain effective mechanism, not causal latency.
- A deterministic generated receipt and tracked closeout exist.
- Focused tests, workflow audit, and diff check pass.

## Handoff

On pass or terminal plant negative, activate C5 without adding an unsupported
contact mechanism.
