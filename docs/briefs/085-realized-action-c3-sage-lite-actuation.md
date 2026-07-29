# Brief 085 — Realized-Action C3 SAGE-Lite Actuation

Decision: `CONTINUE`

Evidence anchor: `104`

## Active card

C3 from the realized-action outcome calibration queue.

## Required slice

Use the frozen `EpisodeTwinBundle.v1` cohorts without opening hardware:

- keep requested, gateway-sent, measured, and timestamp lanes separate;
- report requested-to-sent deltas, sent-to-measured residuals, empirical
  velocity and slew saturation, steady-state undertravel,
  direction-conditioned residuals, return residuals, supported sample-domain
  alignments, and current-register association for every joint;
- label the current register as an uncalibrated association proxy, never force
  or torque;
- compute end-effector residual contribution using the current frozen
  kinematics;
- report fit, validation, and sealed cohorts independently;
- rank mechanisms and joints without using the sealed mission result to select
  a model.

## Verification gate

- Source tensor hashes and whole-episode cohort membership remain unchanged.
- Every statistic has an episode and sample denominator.
- Alignment is labeled sample-domain association, not causal latency.
- Missing actuator application or acknowledgement timing remains explicit.
- The sealed mission episode is report-only.
- A deterministic generated receipt and tracked closeout exist.
- Focused tests, workflow audit, and diff check pass.

## Handoff

On completion, activate C3A first-divergence attribution.
