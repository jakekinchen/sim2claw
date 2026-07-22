# Executor Session Log 015 - SAIL Mechanism-Specific Invariance

**Date:** 2026-07-22

## Slice

P1-08 — implement plugin-declared whole-episode invariance.

## Implemented

- Frozen eight-family context vocabulary and plugin-covariate mapping.
- Whole-episode leakage prevention and minimum context coverage gates.
- Per-episode conditional parameter fits, residual signatures, range, and
  sign-consistency diagnostics.
- `pass_declared_scope`, `fail_context_specific`, and `not_evaluable`
  verdicts with explicit reasons.
- Seeded stable, context-specific, and insufficient-context controls.
- Retained ten-plugin coverage inventory with zero unjustified passes.
- Config/compiler/source/output-bound deterministic receipt and GOLD-11.

## Validation

- Focused invariance tier: 27 passed.
- Complete SAIL tier: 93 passed.
- Broad tier: 700 passed, three skipped, all 328 subtests passed.
- Repeated compilation, Python compilation, receipt verification, and
  whitespace checks: pass.

## Known limitations

The retained evidence has no whole-episode group posteriors and does not span
several declared contexts. All retained mechanisms therefore remain
`not_evaluable`. The seeded pass demonstrates evaluator behavior only, not a
retained invariance or physical-cause result.
