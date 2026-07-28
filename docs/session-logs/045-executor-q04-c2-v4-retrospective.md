# Executor log 045: Q04 immutable C2 replay under v4

Date: 2026-07-27

Decision: Q04 diagnostic acceptance checks passed; outcome remains negative.

## Side-by-side

| Metric | Old scene | v4 |
| --- | ---: | ---: |
| Minimum gripper/pawn-center clearance | `312.326353 mm` | `75.624879 mm` |
| Selected-pawn contact count | `0` | `0` |
| Maximum pawn rise | `0 mm` | `0 mm` |
| Maximum planar pawn displacement | effectively zero | `0.0000075 mm` |
| Off-source consequence | false | false |
| Wrong-piece contact count | not observed | `0` |

The v4 closest point occurs at canonical row `247`, substep `1`. The first
divergence from physical evidence remains: v4 is still `75.625 mm` from the
physical C2 pawn and never establishes simulated contact, while the immutable
physical receipt records strike/topple near C2.

## Commands

```text
uv run --offline pytest -q \
  tests/test_bidirectional_c2_v4_replay.py \
  tests/test_bidirectional_scene_registration_v4.py
.....                                                                    [100%]
5 passed in 1.46s

uv run --offline python \
  scripts/evaluate_bidirectional_c2_v4_replay.py \
  --output \
  runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json
36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664
```

The action remains `701 x 6` little-endian float64 at 40 Hz with raw SHA-256
`0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da`.

## Claim boundary

Proof class: `post_outcome_scene_correction_exact_action_diagnostic`.

The result is a retrospective post-outcome scene correction. It is not
registration admission, simulator task success, physical task success, or
transfer evidence. No motion, camera access, training, or paid compute
occurred.
