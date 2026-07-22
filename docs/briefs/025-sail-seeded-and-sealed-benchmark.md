# Slice Brief 025 - SAIL Seeded and Sealed Structural Benchmark

**Date:** 2026-07-22

## Objective

Complete P1-10 by building a deterministic structural benchmark with disjoint
public and sealed bytes, eight required fault families, single and compensating
faults, context specificity, missing observables, distractor history, oracle
influence sets, frozen controls, and all 25 golden-case integration checks.

## Acceptance Criteria

- Timing, reset/reference, deadband, load compliance, camera, gripper/contact
  geometry, contact/friction/compliance, and object/support faults are present.
- Every case binds baseline, public observations, allowed probes, parameter
  envelopes, hidden mechanisms, sealed rows, and oracle influence sets.
- Public/sealed bytes are disjoint and leakage-tested before method execution.
- Actions and evaluator state are immutable across methods.
- Oracle repair beats unchanged and incorrect controls.
- Required deterministic and ablation baselines are scored under one evaluator.
- Primary structure, influence, residual, regret, efficiency, trigger,
  promotion, debt, recomputation, calibration, and TwinWorthiness metrics are
  emitted.
- Repeated materialization is byte-identical and all synthetic golden cases
  pass.

## Expected Files

- `configs/sail/seeded_benchmark_v1.json`
- `src/sim2claw/sail/benchmark.py`
- `tests/test_sail_benchmark.py`
- ignored `outputs/sail/seeded-benchmark-v1/`
- P1-10 run/session/reviewer logs

## Test Plan

Generate source-public and sealed rows from separate seed domains, scan for
byte/hash/ID overlap, run oracle/unchanged/incorrect controls, score nine
declared methods and ablations, verify action/evaluator identities, aggregate
the primary metrics, run the 25-case registry against its exact tests, and
repeat compilation for tree identity.

## Stop Conditions

- Any public/sealed identity or byte overlap.
- Method-visible hidden mechanism or sealed evaluator state.
- Action or evaluator mutation.
- Oracle control does not beat unchanged and incorrect controls.
- A method wins through leakage, promotion authority, or post-hoc thresholds.
