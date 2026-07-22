# SAIL Structural Surprise and Compensation Debt Run Log

Date: 2026-07-22

Milestone: P1-05

Proof class: deterministic retrospective structure-search diagnostic

## Commands

```bash
uv run sim2claw sail-compile-structural-surprise --config configs/sail/structural_surprise_retired_bg_v1.json --output outputs/sail/retired-bg-v1/structural-surprise
uv run pytest -q tests/test_sail_contracts.py tests/test_sail_evidence.py tests/test_sail_residuals.py tests/test_sail_belief_graph.py tests/test_sail_surprise.py
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Frozen identities

- Configuration: `e8a5ec6df5da7c6c71c112879757663dfc6701f57d6b38067be0338e6815d979`
- Diagnostic: `ce8aae9a9f68a9958fd50e2efd0cd8b4bd20e7dab41d91b5d2369ba206912f54`
- Diagnostic digest: `637288bdc1f673d403ed14cc2f390beb9da914b97a87b27af817dc97a98f4fac`
- Mechanism request: `fa1c8f167845812b6d08b1a4436641368c4f9912a415dde52c38e6368d845308`
- Clean seeded calibration: `66d08fc76cb2d45534f03067b2d1f205c6c6a00b2ee9d974d656b029fb7a36cc`
- Receipt: `8738ec571193a02e7b5ef753e7becddae3f0ee32462f564290c435faf599763c`
- Receipt digest: `37d5eaa8a7d58c30ec3564c97cfbd6106ccf194186af4918179c64f0635ad237`
- Deterministic tree digest: `cdf1b333000140b6c00c355c386afc00d26285a59f35ed8f4af2ed8bdf30d756`

## Diagnostic result

- Retained normalized debt: 0.942857 over 0.70 available weight; threshold
  0.60.
- Trigger contributors: frozen-boundary pressure, cross-family regression,
  persistent event-timing structure, simulator-outcome/trace regression, and
  ensemble coverage without a single winning candidate.
- Posterior drift, phase inconsistency, and posterior correlation remain null
  until P1-06 rather than being scored as zero.
- Six retained physical/object/contact/consequence channels are unavailable;
  `missing_observable` is the primary class while parameter and structural
  uncertainty remain explicit.
- The named load coefficient is a probable historical absorber, not a claimed
  physical cause.

## Validation result

- GOLD-05: pass.
- Clean calibration: zero false triggers across 256 frozen-seed cases; ceiling
  0.01.
- Focused SAIL tier: 48 passed.
- Complete repository: 668 passed, three expected skips, 328 subtests passed in
  1,231.30 seconds.
- Repeated compilation and tree identity match byte-for-byte.

## Claim boundary

Compensation debt requests bounded structure search. It does not identify a
physical mechanism, select a simulator, or grant downstream authority. The
request is deterministic and no-agent.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
