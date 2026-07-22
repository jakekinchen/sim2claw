# Slice Brief 023 - SAIL Mechanism-Specific Invariance

**Date:** 2026-07-22

## Objective

Complete P1-08 by evaluating only the invariance claims declared by each
mechanism plugin, across whole-episode context groups, with explicit
`not_evaluable` results wherever retained or seeded evidence does not span a
required context.

## Product / Project Value

Loop closure can fit the right synthetic structure and still overgeneralize a
context-specific absorber. Scoped invariance prevents a parameter that works
in one direction, load, board region, object, camera, session, or workcell from
being promoted as universal without the required coverage.

## Acceptance Criteria

- Direction, frequency, joint pose/load, board region, object identity, camera
  condition, session, and workcell are available as declared covariates.
- Each plugin declares invariant parameters and permitted/session-local
  covariates; no global invariance assumption is introduced.
- Whole-episode grouping prevents row leakage.
- Parameter and residual-signature stability are tested only across covered
  contexts.
- Missing required context coverage returns a reasoned `not_evaluable`, not a
  pass or imputed value.
- A seeded context-specific mechanism fails universal invariance while a
  seeded stable mechanism passes its declared scope.
- Retained results are labeled retrospective consistency only.
- GOLD-11 passes.

## Expected Files

- `configs/sail/invariance_v1.json`
- `src/sim2claw/sail/invariance.py`
- `tests/test_sail_invariance.py`
- ignored `outputs/sail/retired-bg-v1/invariance/`
- P1-08 run/session/reviewer logs

## Test Plan

Freeze whole-episode grouped fixtures spanning direction and load, plus a
single-workcell retained-coverage inventory. Test plugin-specific scope,
episode disjointness, stable and context-specific parameters, residual
signature consistency, missing-context abstention, deterministic bootstrap or
group comparisons, action identity, output/receipt tamper rejection, and
GOLD-11.

## Validation Commands

```bash
uv run pytest -q tests/test_sail_invariance.py tests/test_sail_mechanisms.py tests/test_sail_loop_closure.py
uv run sim2claw sail-compile-invariance --config configs/sail/invariance_v1.json --output outputs/sail/retired-bg-v1/invariance
uv run pytest -q
git diff --check
```

## Evidence To Record

- Config, mechanism, closure, invariance, and receipt identities.
- Context coverage and whole-episode group identities.
- Per-parameter and residual-signature pass/fail/not-evaluable verdicts.
- Seeded false-universal rejection and stable-scope control.
- Retrospective `not_evaluable` reasons, GOLD-11, and focused/broad results.

## Out Of Scope

- Acquiring missing contexts or choosing the next probe (P1-09).
- Treating retrospective consistency as fresh validation.
- New physical data, hardware/provider access, paid compute, training, policy
  selection, or TwinWorthiness promotion.

## Stop Conditions

- Context groups leak rows from one episode across comparison roles.
- A plugin is tested against an undeclared global invariance scope.
- Missing context is imputed or labeled pass.
- A seeded context-specific mechanism is promoted as universal.
- Source actions, retained results, or unaffected posterior identities change.
