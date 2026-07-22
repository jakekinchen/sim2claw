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
