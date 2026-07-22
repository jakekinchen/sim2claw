# SAIL Influence Discovery and Sparse Loop Closure Run Log

Date: 2026-07-22

Milestone: P1-07

Proof class: retrospective influence nomination plus deterministic synthetic
sparse/full/no-revisit oracle comparison

## Commands

```bash
uv run sim2claw sail-compile-loop-closure --config configs/sail/loop_closure_v1.json --output outputs/sail/retired-bg-v1/loop-closure
uv run pytest -q tests/test_sail_influence.py tests/test_sail_loop_closure.py tests/test_sail_belief_graph.py tests/test_sail_mechanisms.py
uv run pytest -q $(rg --files tests | rg '/test_sail_.*\\.py$' | sort)
uv run pytest -q
uv run python -m compileall -q src tests
git diff --check
```

## Frozen identities

- Configuration: `1b5719122e60fc1d62f3fb82fd1e1fbdc4e60c0f9343764af322fdc6e38ad648`
- Influence set: `c8f414252314b498c9c9d0f29c68b86531e20708b65c0dc92ec4d2e7c75ea10c`
- Sparse closure: `249c93e4cb077ca545e4012a553dd72081eda0b2e871d21c48e639fd3a420fe0`
- Closure digest: `bb5c6299c979e270b92e9812fd15b1b3900aae2f80e13cfb98992e2c445fd949`
- Receipt: `9f7bef6aba4d233e5d727c3015f328b715b2c9660828cb7d4c3f7b89f137c64a`
- Receipt digest: `416473a24eb49dd0bd6abefa5666b8b580c765bf76db33c13714f5db38be1eb4`
- Deterministic tree digest: `1db84966fa4c84ca43f1993ffb59d51ceb61d5d8336acaab7ad930a02432219d`

## Influence result

- Twelve retained intervention candidates were evaluated using declared scope,
  graph `predicts` paths, residual-family overlap, and retained intervention
  residual-coverage sensitivity.
- Exactly `intervention:load-bias-boundary` and
  `intervention:fidelity-rms-closeout` were nominated.
- Oracle precision and recall are both 1.0; timing, deadband, geometry, and
  contact distractors remain excluded even when their residuals overlap.

## Sparse closure result

- The seeded compensating timing estimate moves from 0.98193 to 0.15 after
  adding the true 0.8 load term and refitting only the affected pair.
- Compensation debt falls from 1.63193 to numerical zero.
- Sparse SSE is 0.0001 and differs from full-batch SSE by only 5.29e-15
  fractionally.
- Sparse closure recomputes 2/8 decisions; full batch recomputes 8/8.
- The sequential no-revisit estimate recovers load as only 0.045997 and fails
  structure recovery.
- All unaffected posterior digests, source action bytes, and frozen evidence
  bytes remain unchanged.

## Validation result

- GOLD-09 and GOLD-10: pass.
- Focused influence/closure/graph/mechanism tier: 34 passed.
- Complete SAIL tier: 86 passed.
- Complete repository: 693 passed, three expected skips, 328 subtests passed
  in 1,234.06 seconds.
- Repeated compilation and output-tree identities match byte-for-byte.

## Claim boundary

The retained influence result nominates historical decisions; it does not
refit or revise them. Credit reassignment and sparse/full superiority are
demonstrated on a seeded synthetic fixture, not as physical causal
identification or simulator promotion.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
