# Slice Brief 020 - SAIL Structural Surprise and Compensation Debt

**Date:** 2026-07-22

## Objective

Complete P1-05 by producing normalized, auditable structural-surprise and
compensation-debt diagnostics from the P1-03 residual field and P1-04 belief
graph, without converting diagnostic patterns into physical-cause claims.

## Product / Project Value

This gate decides when another parameter sweep is conceptually unsafe because
an existing parameter is likely absorbing missing structure. It converts the
retained campaign's mixed trace/contact outcomes into a bounded mechanism
request instead of permitting endless compensating fit.

## Acceptance Criteria

- Frozen-boundary selection, cross-family regression, parameter drift/reversal,
  phase/context inconsistency, persistent structure, posterior correlation,
  simulator/trace divergence, and ensemble-without-single-winner signals have
  normalized components with source evidence.
- The trigger rule, thresholds, weights, missing-data behavior, and dominant
  contributors are deterministic and auditable.
- Diagnostics distinguish `parameter_uncertainty`, `structural_uncertainty`,
  and `missing_observable`.
- The retained load-boundary and mixed trace/contact history triggers a
  no-agent mechanism request without asserting a physical cause.
- Clean seeded parameter-only fixtures stay below the frozen false-trigger
  ceiling.
- GOLD-05 passes.

## Expected Files

- `configs/sail/structural_surprise_retired_bg_v1.json`
- `src/sim2claw/sail/structural_surprise.py`
- `tests/test_sail_structural_surprise.py`
- ignored `outputs/sail/retired-bg-v1/structural-surprise/`
- P1-05 run/session/reviewer logs

## Test Plan

Start with isolated synthetic signals, threshold boundaries, missing values,
clean seeded false-trigger calibration, category classification, deterministic
component aggregation, and causal-claim prohibitions. Then compile the retained
diagnostic and verify the request packet and receipt twice.

## Validation Commands

```bash
uv run pytest tests/test_sail_structural_surprise.py tests/test_sail_contracts.py -q
uv run sim2claw sail-compile-structural-surprise --config configs/sail/structural_surprise_retired_bg_v1.json --output outputs/sail/retired-bg-v1/structural-surprise
uv run pytest -q
git diff --check
```

## Evidence To Record

- Frozen config/source/diagnostic/request/receipt hashes.
- Per-component normalized scores, trigger contributors, and uncertainty class.
- Seeded clean-case false-trigger count/rate and GOLD-05 result.
- Focused/broad results and resource closeout.

## Out Of Scope

- Identifying a physical mechanism or parameter.
- Fitting P1-06 mechanism plugins or posterior particles.
- New physical data, hardware access, provider calls, or paid compute.
- TwinWorthiness promotion, training admission, or policy selection.

## Stop Conditions

- A trigger lacks exact source evidence or a frozen threshold.
- Missing observables are converted to zeros or parameter estimates.
- A diagnostic names an asserted physical cause.
- A clean seeded parameter-only suite exceeds its false-trigger ceiling.
