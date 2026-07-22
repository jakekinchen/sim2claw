# Slice Brief 019 - SAIL Deterministic Belief Graph

**Date:** 2026-07-22

## Objective

Complete P1-04 by compiling the retained evidence and residual identities into
an order-stable, proof-preserving SAIL belief graph with a chronological
revision timeline and a traversable source-action-to-verdict path.

## Product / Project Value

The graph is the explicit causal bookkeeping layer for surprise, compensation
debt, mechanism fitting, loop closure, acquisition, TwinWorthiness, and Studio.
It must keep negative and non-promoted experiments visible instead of reducing
history to the latest favored simulator.

## Acceptance Criteria

- Canonical serialization and graph digest are stable under input reordering.
- Every imported result retains its original proof class, evaluator identity,
  source binding, and promotion status.
- Workcell/context, evidence/residual, simulator, mechanism/posterior,
  intervention/candidate, verdict/certificate, policy lineage, and
  counterexample node families are representable.
- All eleven declared edge families are validated and queryable.
- Geometry/scale, reset, timing, deadband, load response, contact ensemble,
  timestep, fixed-pad, friction, and terminal evaluator history is represented
  chronologically without promoting negative results.
- Declared intervention scopes generate influence candidates before any
  statistical similarity is considered.
- A current retained action can be traversed through evidence and candidate
  lineage to its terminal evaluator verdict.
- Before/after graph revisions are emitted as read-only JSON and SVG views.

## Expected Files

- `configs/sail/belief_graph_retired_bg_v1.json`
- `src/sim2claw/sail/belief_graph.py`
- `src/sim2claw/sail/belief_visuals.py`
- `tests/test_sail_belief_graph.py`
- ignored `outputs/sail/retired-bg-v1/belief-graph/`
- P1-04 run/session/reviewer logs

## Test Plan

Start with node/edge vocabulary, duplicate-ID, dangling-edge, order-stability,
proof/evaluator preservation, negative-query, scope-first influence, and
source-action-to-verdict traversal fixtures. Then compile and verify the
retained chronological graph twice before the broad regression gate.

## Validation Commands

```bash
uv run pytest tests/test_sail_belief_graph.py tests/test_sail_contracts.py -q
uv run sim2claw sail-compile-belief-graph --config configs/sail/belief_graph_retired_bg_v1.json --output outputs/sail/retired-bg-v1/belief-graph
uv run pytest -q
git diff --check
```

## Evidence To Record

- Configuration, source, graph, revision, visualization, and receipt hashes.
- Node/edge counts by type, retained negative count, and proof-class counts.
- Canonical order-repeat identity and graph traversal evidence.
- Focused/broad results and resource closeout.

## Out Of Scope

- Statistical mechanism fitting, posterior updates, or causal promotion.
- New physical data, hardware access, provider calls, or paid compute.
- Treating graph connectivity as causal evidence.
- TwinWorthiness promotion, training admission, or policy selection.

## Stop Conditions

- A source result loses its proof class, evaluator, or negative status.
- A graph edge invents lineage not declared by a bound source.
- Input ordering changes the canonical graph digest.
- The source-action-to-verdict route is missing or ambiguous.
