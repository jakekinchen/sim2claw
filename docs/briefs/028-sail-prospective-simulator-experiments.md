# Slice Brief 028 - SAIL Prospective Simulator Experiments

**Date:** 2026-07-22

## Objective

Complete P1-13 by preregistering competing mechanisms and expected residual
signatures, selecting graph-native simulator interventions through the frozen
acquisition router, preserving the retained action arrays byte-for-byte, and
freezing the final simulator/posterior family before Phase 2.

## Acceptance Criteria

- Mechanisms, expected residual changes, intervention order, budgets, stop
  rules, and evaluator identities are frozen before execution.
- Only declared simulator-native probes run; hardware plans remain unavailable.
- Every variant binds the same action shapes, dtype, ordering, values, and
  hashes, and the full residual/consequence vector is evaluated.
- Predicted and observed simulator residual changes, loop-closure next-probe
  decisions, negative/stopped candidates, and boundary results are retained.
- No parameter grid expands after observing a frozen boundary result.
- The final simulator/posterior family and Phase 2 predictions are content-
  addressed and frozen before any future physical observation is opened.

## Stop Conditions

- An action, evaluator, preregistration, or held-out boundary changes after the
  first simulator execution.
- A candidate outside the declared family or budget is run.
- A stopped/negative result is omitted or a boundary triggers post-hoc search.
- The experiment claims new physical truth, opens TW-DATA, trains a policy, or
  invokes hardware.

## Result

Completed. The protocol and all source identities were committed before the
first run. The acquisition router's rank-1 structural probe was executed as a
four-trial 2x2 simulator-side command-frequency/load-response factorial on one
retained episode. Every trial consumed the same contiguous 368x6 float64
action tensor with SHA-256
`c4acc4dca04e30c9d3031e326496a7c1d46777e7a1bd87b8d6968d2174e575bc`;
no action value, row, dtype, order, clip, offset, IK correction, suffix, or
assistance changed.

All four declared trials completed with zero retries, zero undeclared trials,
zero stopped results, and no post-hoc expansion. The timing family matched both
required prospective signatures (score 1.0); the load family matched its
stationary elbow RMS and signed-bias signatures but not its locality signature
(score 2/3). Loop closure therefore selected the separately preregistered
`sim_timing_rate_probe` next. The load-intervention trial remained the lowest-
RMS simulator diagnostic. All controls and nonselected trials remain retained,
and the full residual vector and explicit unavailable consequence channels are
preserved.

The graph delta, posterior family, selected simulator diagnostic, and three
Phase 2 predictions are content-addressed. No physical observation was opened.
The result does not identify latency, load/compliance, contact, or any other
physical parameter; it does not promote a simulator or open TW-DATA, training,
policy selection, canary, motion, or transfer authority.
