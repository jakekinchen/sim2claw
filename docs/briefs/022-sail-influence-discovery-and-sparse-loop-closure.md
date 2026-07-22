# Slice Brief 022 - SAIL Influence Discovery and Sparse Loop Closure

**Date:** 2026-07-22

## Objective

Complete P1-07 by discovering the minimal historical decision set affected by
a proposed mechanism and closing only that subgraph, while comparing the
sparse result with a frozen full-batch oracle and sequential no-revisit
baseline.

## Product / Project Value

Sparse loop closure is the core ClawLoop credit-reassignment step. It must show
that a newly supported structure can remove compensation debt without silently
rewriting unaffected decisions or requiring a full campaign recomputation.

## Acceptance Criteria

- Influence discovery combines declared intervention scope, plugin influence
  edges, belief-graph reachability, residual-family overlap, and local
  sensitivity with frozen deterministic thresholds.
- Seeded affected-set precision and recall cross their frozen thresholds.
- Sparse closure removes the compensating contribution, adds the supported
  mechanism, refits only the nominated subgraph, and preserves immutable source
  actions and frozen historical results.
- Unaffected posterior identities remain byte-identical.
- Sparse closure is materially equivalent to full-batch oracle score while
  recomputing fewer decisions, and outperforms sequential no-revisit structure
  recovery on the seeded benchmark.
- Material sparse/full disagreement fails closed.
- GOLD-09 and GOLD-10 pass.

## Expected Files

- `configs/sail/loop_closure_v1.json`
- `src/sim2claw/sail/influence.py`
- `src/sim2claw/sail/loop_closure.py`
- `tests/test_sail_loop_closure.py`
- ignored `outputs/sail/retired-bg-v1/loop-closure/`
- P1-07 run/session/reviewer logs

## Test Plan

Freeze seeded graph fixtures with oracle influence sets, decoys, and one
compensating parameter. Test exact scope nomination, graph reachability,
residual overlap, local sensitivity, no-op/abstention behavior, action and
unaffected-posterior identity, sparse/full score agreement, recomputation
ratio, sequential-baseline failure, deterministic regeneration, and receipt
tamper rejection.

## Validation Commands

```bash
uv run pytest -q tests/test_sail_loop_closure.py tests/test_sail_belief_graph.py tests/test_sail_mechanisms.py
uv run sim2claw sail-compile-loop-closure --config configs/sail/loop_closure_v1.json --output outputs/sail/retired-bg-v1/loop-closure
uv run pytest -q
git diff --check
```

## Evidence To Record

- Configuration, graph, mechanism, benchmark, closure, and receipt hashes.
- Oracle affected sets and precision/recall.
- Sparse/full/sequential structure-recovery scores and recomputation counts.
- Before/after debt, residual, posterior, graph, and action identities.
- GOLD-09/10 and focused/broad results.

## Out Of Scope

- Claiming a retained physical mechanism is identified.
- Mechanism-specific cross-context invariance (P1-08).
- Intervention acquisition or provider/agent campaigns (P1-09/P1-11).
- New physical data, hardware access, paid compute, training, policy selection,
  or TwinWorthiness promotion.

## Stop Conditions

- Any source action or frozen historical result changes.
- An unaffected posterior identity changes.
- Sparse/full score disagreement crosses the frozen tolerance.
- Influence recall or precision falls below its frozen threshold.
- Missing observables are imputed or incompatible structures are averaged.
