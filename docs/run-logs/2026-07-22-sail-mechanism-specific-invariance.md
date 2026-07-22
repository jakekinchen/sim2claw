# SAIL Mechanism-Specific Invariance Run Log

Date: 2026-07-22

Milestone: P1-08

Proof class: deterministic seeded whole-episode invariance fixtures plus
retrospective context-coverage inventory

## Commands

```bash
uv run sim2claw sail-compile-invariance --config configs/sail/invariance_v1.json --output outputs/sail/retired-bg-v1/invariance
uv run pytest -q tests/test_sail_invariance.py tests/test_sail_mechanisms.py tests/test_sail_loop_closure.py
uv run pytest -q $(rg --files tests | rg '/test_sail_.*\\.py$' | sort)
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Frozen identities

- Configuration: `d067354d78a5784a407d5698a35bf5c5c1ac8e7ce76725b81efdcf21564bbaae`
- Seeded invariance: `55398d1f45c17346e57f96ba85fc1258e234ffe8d9fce2716d0ace6953756a53`
- Seeded benchmark digest: `040a0be361008f3886e5bedec757667a17a32e575cfe9c8ad463cfec81638b0a`
- Retained inventory: `6d02eba1e18c1566aaf6113c3a60b9e6122dc82a0dc8d05704a9a06de4654e88`
- Retained inventory digest: `c5513af152b5f48e7d34bd1a5f0bf5255a0583ba6a3260baf1b67ad0257cc490`
- Receipt: `16eb4ded87e476f48ce60be49fb2fa970983f0cdbf4e50b6b1953c74c4c1c753`
- Receipt digest: `03a4ff00bd0ad9cd48f612e4d6e8190966a13385bff454889b73985a6d3983b1`
- Deterministic tree digest: `8499524b2163ea8f6c3116ca78e4b6685fd03681340fe6f9c8043bc6baee2b65`

## Seeded result

- A timing parameter stable across 20 Hz and 30 Hz passes its declared scope;
  fitted episode range is 0.001006 with sign consistency 1.0.
- A load coefficient varying between approach and transport fails universal
  invariance; fitted episode range is 0.70042 despite sign consistency 1.0.
- A camera parameter observed under only one camera returns `not_evaluable`.
- Whole episodes are disjoint and source action bytes remain unchanged.
- GOLD-11 passes; the context-specific mechanism is not promoted universal.

## Retained result

- All ten plugin-declared invariance checks return `not_evaluable`.
- Five lack required observables, three lack whole-episode group posteriors,
  and two lack at least two covered context levels.
- Retained data provide retrospective consistency inventory only; zero
  invariance passes and zero fresh-validation claims are issued.

## Validation result

- Focused invariance/mechanism/closure tier: 27 passed.
- Complete SAIL tier: 93 passed.
- Complete repository: 700 passed, three expected skips, 328 subtests passed
  in 1,231.23 seconds.
- Repeated compilation and output-tree identities match byte-for-byte.

## Claim boundary

GOLD-11 establishes the evaluator's ability to pass stability, reject
context-specificity, and abstain on insufficient coverage. It does not make the
retained mechanisms invariant or physically identified.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
