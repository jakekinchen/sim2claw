# Slice Brief 016 - SAIL Contracts and Golden Oracles

**Date:** 2026-07-21

## Objective

Complete P1-01 by freezing the five SAIL v1 schemas, subordinate golden
documents, TwinWorthiness truth table and thresholds, benchmark identities and
splits, proof vocabulary, and GOLD-00 through GOLD-24 oracle fixtures before
any prospective SAIL simulator result is generated.

## Product / Project Value

This slice makes later results incapable of silently redefining evidence,
mechanisms, interventions, certificates, sealed evaluation behavior, or
downstream admission.

## Acceptance Criteria

- Five schemas validate canonical positive fixtures and reject malformed or
  authority-violating fixtures.
- All 25 golden cases have immutable IDs, expected verdicts, proof classes, and
  named tests.
- TwinWorthiness levels and `pass`/`fail`/`not_evaluable` semantics are frozen.
- Benchmark fault families, seeds, public/sealed split, budgets, metrics, and
  negative controls are frozen before implementation or new results.
- GOLD-00 through GOLD-04, GOLD-13 through GOLD-15, and GOLD-19 through GOLD-24
  pass in focused tests.
- Existing retained evidence and generated artifacts remain untouched.

## Expected Files

- `configs/sail/schemas/*.json`
- `configs/sail/twin_worthiness_v1.json`
- `configs/sail/benchmark_v1.json`
- `docs/golden/sail/*.md`
- `tests/fixtures/sail/*.json`
- `tests/test_sail_contracts.py`
- `tests/test_sail_twin_worthiness.py`
- `tests/test_sail_hardware_protocol.py`

## Test Plan

Begin with contract and authority negative tests. Add canonical digest,
availability-mask, action-byte, sealed-access, provider-identity, workcell
identity, and hardware-authority cases before production code.

## Validation Commands

```bash
uv run pytest tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py -q
uv run pytest -q
python -m json.tool configs/sail/benchmark_v1.json >/dev/null
python -m json.tool configs/sail/twin_worthiness_v1.json >/dev/null
git diff --check
```

## Evidence To Record

- Schema/config hashes.
- Golden-case registry hash and test mapping.
- Focused and broad test counts.
- Proof that sealed fixtures are generated or read only through evaluator-owned
  paths.
- Session log and reviewer verdict.

## Reachability / Demo Proof

Load every schema and campaign config from the existing `sim2claw` runtime and
exercise the frozen truth table through repository tests.

## Cross-Doc Impact

Update the master-plan ledger, `GOAL.md`, project state, and orchestration ledger
only after every P1-01 acceptance criterion passes.

## Out Of Scope

- Retained evidence import.
- Residual computation.
- Mechanism fitting or loop closure.
- Provider model calls.
- New simulator results.
- Physical capture or motion.

## Stop Conditions

- A required contract cannot preserve action or evaluator invariance.
- A schema would impute an unavailable observation.
- Sealed evaluator bytes would become agent-visible.
- A threshold or split cannot be frozen without observing the result it grades.
