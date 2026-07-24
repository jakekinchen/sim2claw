# Executor session 031: actuator external-validation preregistration

Date: 2026-07-23

Milestone: `D6_ACTUATOR_EXTERNAL_VALIDATION_PREREGISTERED`

## Frozen question

Does the already selected action-frozen servo deadband/load-response candidate
retain a material joint-trace benefit on the five separately recovered 72 mm
historical acquisition sessions, without regressing pooled EE RMS?

This is external trace validation, not a refit. The 11-episode selection
session, five-episode evaluation cohort, and existing independent 0/11 strict
task consequence remain separate proof surfaces.

## Frozen contract

- External cohort: 5 episodes / 2,186 verified rows.
- Variants: existing baseline and the prior selected candidate only.
- Candidate: 0.11 s delay, 1.5 degree shoulder-lift deadband, 2.0 degree elbow
  deadband, and -1.5 elbow load coefficient.
- Budget: 10 simulator replays, 0 retries, 0 provider calls.
- Action contract: float64 `[N, 6]`, byte-identical across variants, no
  clipping, IK, resampling, offsets, suffix, assistance, or reordering.
- Gates: pooled joint-RMS improvement at least 2%; at least 4/5 episode
  improvements; 95% paired whole-session bootstrap lower bound above zero;
  pooled EE RMS no worse than baseline.
- Consequence boundary: external traces cannot modify the existing independent
  task score, promote a parameter, or establish physical calibration/transfer.

The contract SHA-256 is
`3f8b83764741690fca8b73572840e2bc33a862a47fe49fbeb8aee4a4ed951c4c`.
The frozen implementation SHA-256 is
`a9be358cb5753ca2aec38d7de5f50012c4dcd0d1211fa5c249ad27de315fc778`.

## Pre-execution proof

Focused evaluator tests pass `16 / 16`, including fail-closed action,
episode/source, replay, metric, budget, threshold, candidate, scoring, and task
authority mutations. The five live sources map to all 2,186 rows without
clipping. External simulator replay usage remains `0 / 10`.
