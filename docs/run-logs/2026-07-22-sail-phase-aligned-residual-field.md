# SAIL Phase-Aligned Residual Field Run Log

Date: 2026-07-22

Milestone: P1-03

Proof class: deterministic retrospective residual compilation

## Commands

```bash
uv run sim2claw sail-compile-residuals --config configs/sail/residual_field_retired_bg_v1.json --output outputs/sail/retired-bg-v1/residuals
uv run pytest -q tests/test_sail_contracts.py tests/test_sail_evidence.py tests/test_sail_residuals.py
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

`ruff` is not installed in the locked runtime, so no linter result is claimed.
Compilation, focused tests, the complete suite, and whitespace checks passed.

## Frozen identities

- Configuration: `15f09f4b4d376bcda96199924fea573a65787c4d6fe47fcdd631b741ae60a79c`
- Residual field: `38a78aa325ccb978e131ac087e6820c35faa4473172387d5f738261ff1889c71`
- Receipt: `4022b6a1f11b326cdc980f022d2c1fd6eaaa279ab28ae152ac4b4675326c6203`
- Receipt digest: `3113c19f74f563d67d45817f56bd539faa65da51a3a600634de0c5191415ffe7`
- Deterministic tree digest: `3be532d714973ab010cbbb007e23517ab2eb4862d93969768afdfe583f53cccd`
- Heatmap JSON: `f7f7a281e41c76adeca4108dc3d82bb8ec0d6bb0cc38b839c0179e119ede3e49`
- Heatmap SVG: `4af7b75b76c60bab4498af619a0161c21793008ec501b11fc1cdb91a14b28dae`
- Episode drilldowns: `9714c9b508dec122ac124b8b09b56c7050a25c32cc144e5a98eced4db4b710be`

## Compilation result

- 11 action-frozen development episodes and 4,743 exactly aligned source rows.
- 213,897 scalar residual samples and 3,630 episode/phase/channel summaries.
- 57 deterministic 10,000-replicate whole-episode bootstrap estimates.
- Six explicit unavailable channel families, emitted once per phase with null
  values and false availability masks rather than imputation.
- Physical gripper position and velocity retain recorded-percent units; body
  joints retain degree units; simulator joints retain radians.
- All six event-timing differences remain explicit, including nonzero shifted
  near-close and release timings where a shared minimum would be misleading.

## Validation result

- Focused SAIL evidence, residual, and contract tier: 30 passed.
- Complete repository: 650 passed, three expected skips, 328 subtests passed in
  1,231.49 seconds.
- Repeated compilation produced identical output and tree digests.
- Receipt verification binds configuration, compiler code, outputs, authority,
  and canonical receipt digest.

## Claim boundary

P1-03 exposes retained phase/timing mismatch. It does not identify a physical
mechanism, infer missing contact/object observations, promote a simulator,
admit training, select a policy, or establish physical transfer.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
