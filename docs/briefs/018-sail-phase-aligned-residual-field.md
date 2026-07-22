# Slice Brief 018 - SAIL Phase-Aligned Residual Field

**Date:** 2026-07-21

## Objective

Complete P1-03 by turning the P1-02 evidence catalog into deterministic,
phase-aligned `ResidualField.v1` artifacts without collapsing timing error,
inventing unavailable contact/object channels, or changing action bytes.

## Product / Project Value

The residual field is the observable gap surface consumed by the belief graph,
structural-surprise rules, mechanism plugins, TwinWorthiness, and Studio. It
must preserve complete curves and provenance rather than only pooled minima.

## Acceptance Criteria

- Observable command, closure, transport-candidate, release, and retraction
  phases are stable and have source time-base provenance.
- Command-to-measured physical and mapped-real-to-simulator joint/EE residuals
  retain complete curves, units, frames, masks, and source evidence IDs.
- Resampling declares interpolation and never fills an unavailable channel.
- Phase/event timing error remains visible when trajectories share a minimum.
- Whole-episode bootstrap intervals are deterministic under the frozen seed.
- Contact/object/consequence channels abstain when the retained source lacks
  the required observation.
- GOLD-03 and GOLD-04 pass through the compiled retained path.

## Expected Files

- `configs/sail/residual_field_retired_bg_v1.json`
- `src/sim2claw/sail/phases.py`
- `src/sim2claw/sail/residuals.py`
- `src/sim2claw/sail/residual_visuals.py`
- `tests/test_sail_residuals.py`
- ignored `outputs/sail/retired-bg-v1/residuals/`
- P1-03 run/session/reviewer logs

## Test Plan

Start with phase-order, shifted-curve, mask-preservation, unit/frame/provenance,
action-invariance, bootstrap-repeat, and missing-contact fixtures. Then compile
the 11 retained development pairs and verify every output against
`ResidualField.v1`.

## Validation Commands

```bash
uv run pytest tests/test_sail_residuals.py tests/test_sail_contracts.py -q
uv run sim2claw sail-compile-residuals --config configs/sail/residual_field_retired_bg_v1.json --output outputs/sail/retired-bg-v1/residuals
uv run pytest -q
git diff --check
```

## Evidence To Record

- Evidence catalog and residual configuration hashes.
- Episode/phase/channel counts and explicit abstentions.
- Phase alignment, interpolation, bootstrap, and action-invariance identities.
- Residual catalog, plots, and receipt hashes plus regeneration commands.
- Focused/broad results and resource closeout.

## Out Of Scope

- Mechanism fitting, causal attribution, or parameter promotion.
- New physical data, hardware access, provider calls, or paid compute.
- Treating CV/video annotations as metric contact or object ground truth.
- TwinWorthiness promotion or policy data generation.

## Stop Conditions

- A residual requires an unavailable physical channel.
- Resampling loses its time base, unit, frame, or availability mask.
- Source actions differ from P1-02 identities.
- A pooled statistic hides a phase/event timing discrepancy.
