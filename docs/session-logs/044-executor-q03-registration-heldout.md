# Executor log 044: Q03 single-open registration held-out

Date: 2026-07-27

Decision: Q03 metric admission failed; preregistered fallback F1 triggered.

## Frozen result

The v4 candidate remained byte-identical at SHA-256
`c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b`.
The B7 held-out episode was opened once:

| Gate | Result | Limit | Decision |
| --- | ---: | ---: | --- |
| C2 fit | `24.631505 mm` | `25 mm` | pass |
| B7 held-out | `164.353128 mm` | `25 mm` | fail |
| New external perfect-tracking contact pairs | `0` | `0` | pass |

The held-out observed-minus-expected vector was
`[+20.370202, +162.834641, -9.049048] mm`. The dominant error is planar, not
the task-relative hover height.

## Commands

```text
uv run --offline pytest -q \
  tests/test_bidirectional_registration_v4_evaluator.py \
  tests/test_bidirectional_scene_registration_v4.py
.....                                                                    [100%]
5 passed in 0.32s

uv run --offline python \
  scripts/evaluate_bidirectional_registration_v4.py \
  --output \
  runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json
7bfd06be5dd397a8c25dc7a4e3cdadd08fa006271fec38d4abcac27d04c125bf
```

## F1 disposition

No second registration family is permitted. V4 is preserved as a failed
candidate. Before Q05 freezes any action family, the prospective consequence
gate is reduced from destination-square occupancy to the selected pawn base
center being displaced completely off its source square. The push stroke may
be widened. Any later result must be called a bidirectional off-source
displacement primitive, not adjacent-square placement.

Proof class:
`zero_motion_fit_and_single_open_heldout_registration_validation`.

No robot motion, camera access, training, or paid compute occurred.
