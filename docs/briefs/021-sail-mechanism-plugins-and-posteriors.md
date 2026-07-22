# Slice Brief 021 - SAIL Mechanism Plugins and Posterior Fitting

**Date:** 2026-07-22

## Objective

Complete P1-06 by implementing the bounded v1 mechanism ABI/registry and
structure-particle posterior fitter, wrapping current retained candidates
without rewriting their historical results or changing source actions.

## Product / Project Value

Mechanism plugins turn the P1-05 request into executable, falsifiable model
families. Separate structure particles preserve incompatible explanations,
while bounded conditional parameter fits expose uncertainty rather than
averaging mechanisms into one misleading composite.

## Acceptance Criteria

- Timing, deadband, load response, geometry, gripper, fingertip contact,
  contact friction, timestep, and object-property plugins satisfy the frozen
  ABI and registry.
- Every plugin declares required observables, affected residual channels,
  parameter bounds/priors, intervention scope, invariants, and abstentions.
- Bounded fitting and Laplace/bootstrap uncertainty are deterministic and stay
  within declared physical/simulator bounds.
- Structure particles remain separate and unsupported mechanisms abstain.
- Historical wrappers reproduce their source-bound configurations without
  changing historical results or action bytes.
- GOLD-06 through GOLD-08 pass on synthetic fixtures.

## Expected Files

- `configs/sail/mechanism_registry_v1.json`
- `src/sim2claw/sail/mechanisms.py`
- `src/sim2claw/sail/posterior.py`
- `tests/test_sail_mechanisms.py`
- ignored `outputs/sail/retired-bg-v1/mechanisms/`
- P1-06 run/session/reviewer logs

## Test Plan

Start with ABI validation, bounds, required-observable abstention, action
identity, wrapper reproduction, multimodal particle separation, deterministic
optimization, and uncertainty intervals. Implement GOLD-06/07/08 as seeded
load, contact, and camera-timing/extrinsic structure-recovery fixtures, then
compile retained wrappers twice before the broad regression gate.

## Validation Commands

```bash
uv run pytest tests/test_sail_mechanisms.py tests/test_sail_contracts.py -q
uv run sim2claw sail-compile-mechanisms --config configs/sail/mechanism_registry_v1.json --output outputs/sail/retired-bg-v1/mechanisms
uv run pytest -q
git diff --check
```

## Evidence To Record

- Registry/plugin/source/wrapper/posterior/receipt hashes.
- Plugin count, abstention count, particle count, bounds, and uncertainty mode.
- Action-identity and historical-wrapper reproduction evidence.
- GOLD-06/07/08 and focused/broad results.

## Out Of Scope

- Sparse loop closure or credit reassignment (P1-07).
- Claiming a retained mechanism is physically identified.
- New physical data, hardware access, provider calls, or paid compute.
- TwinWorthiness promotion, training admission, or policy selection.

## Stop Conditions

- A plugin changes source actions or historical result bytes.
- A posterior sample leaves its declared bounds.
- Missing required observables are imputed rather than causing abstention.
- Incompatible structures are averaged into one parameter vector.
