# Slice Brief 024 - SAIL Structural-Discrimination Acquisition

**Date:** 2026-07-22

## Objective

Complete P1-09 by ranking simulator-native and future hardware interventions
for expected structural discrimination, while keeping structure entropy,
compensation-debt reduction, gate relevance, parameter refinement, cost, risk,
and availability explicit and separate.

## Product / Project Value

The next experiment should separate competing mechanisms, not merely improve a
shared score under both. A deterministic acquisition router turns the current
uncertainty and `not_evaluable` reasons into bounded, auditable probe plans.

## Acceptance Criteria

- Each candidate declares predicted signatures by structure, expected
  structure-entropy reduction, expected compensation-debt reduction, gate
  relevance, parameter-refinement value, cost, risk, proof class, and
  availability.
- Structural discrimination and parameter refinement remain separate scores.
- Simulator-native probes can be ranked for execution over retained actions
  and seeded faults without changing source actions.
- Future hardware probes compile as unavailable plans and are never reported
  as executed.
- Fixed-graph rankings are deterministic and order invariant.
- The router prefers a signature-separating probe over one that improves both
  ambiguous hypotheses equally.
- Random, coordinate-order, residual-magnitude, and parameter-uncertainty
  baselines are compared on a seeded fixture.
- GOLD-12 passes.

## Expected Files

- `configs/sail/acquisition_v1.json`
- `src/sim2claw/sail/acquisition.py`
- `tests/test_sail_acquisition.py`
- ignored `outputs/sail/retired-bg-v1/acquisition/`
- P1-09 run/session/reviewer logs

## Test Plan

Freeze ambiguous structure particles and candidate probes with one
signature-separating simulator intervention, one common-mode improvement, one
parameter-only refinement, distractors, and unavailable hardware plans. Test
score decomposition, deterministic ranking, baseline regret, unavailable-plan
handling, action identity, receipt tamper rejection, and GOLD-12.

## Validation Commands

```bash
uv run pytest -q tests/test_sail_acquisition.py tests/test_sail_invariance.py tests/test_sail_loop_closure.py
uv run sim2claw sail-compile-acquisition --config configs/sail/acquisition_v1.json --output outputs/sail/retired-bg-v1/acquisition
uv run pytest -q
git diff --check
```

## Evidence To Record

- Config, graph, surprise, posterior, invariance, ranking, plan, and receipt
  identities.
- Per-candidate score components and availability verdicts.
- Structural versus parameter-refinement rankings.
- Seeded baseline comparison and GOLD-12.
- Action identity and zero hardware/provider execution.

## Out Of Scope

- Executing any hardware plan or collecting new physical data.
- Provider/agent campaigns (P1-11).
- Opening TwinWorthiness, training, or policy-selection gates.
- Treating an expected score as observed causal evidence.

## Stop Conditions

- A common-mode improvement outranks a stronger structural discriminator
  without an explicit frozen tradeoff.
- Structural and parameter-refinement scores are collapsed into one opaque
  value.
- An unavailable hardware plan is marked executed.
- Ranking changes under input permutation or fixed-seed regeneration.
- Source actions or retained evidence change.
