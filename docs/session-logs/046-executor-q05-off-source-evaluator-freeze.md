# Executor log 046: Q05 native off-source evaluator freeze

Date: 2026-07-27

Decision: Q05 acceptance checks passed.

## Frozen evaluator

Evaluator ID:
`bidirectional_off_source_push_float64_40hz_v1`.

Evaluator SHA-256:
`8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479`.

The F1 consequence is complete selected-pawn displacement off the source
square. With a `44.45 mm` square and `13.8 mm` pawn-base radius, the frozen
signed progress gate is `36.025 mm`. Destination occupancy and final upright
placement are explicitly forbidden claims.

The action boundary is native little-endian float64, C-order, six joints, and
40 Hz. Every case must bind NPY and raw hashes, separate hardware/simulator
mapping hashes, v4 scene hash, evaluator hash, and a separately named setup
prefix hash. Clipping, retiming, offsets, IK repair, assistance, retries, and
corrective suffixes are forbidden.

The complete physical case family is ten one-use slots:

```text
REAL_TO_SIM: R01 G2->G1, R02 E2->E1, R03 H1->H2,
             R04 D1->D2, R05 B1->B2
SIM_TO_REAL: S01 F1->F2, S02 A2->A1, S03 B7->B8,
             S04 D7->D8, S05 F7->F8
```

C2 is excluded. No selected pawn may receive a second physical attempt.
Q06/Q07 may reject an unsafe or unavailable slot before counted motion without
adding it to the physical denominator; the family may not be expanded.

The push stroke is widened to `90-120 mm`. The initial selected pawn must be
upright, exclusions need `88.9 mm` route clearance, excluded C922 centroids
may move at most `4 px`, simulator exclusions at most `1 mm` with zero
contacts, and selected-pawn contact is required.

## Validation

```text
uv run --offline pytest -q tests/test_bidirectional_off_source_evaluator.py
....                                                                     [100%]
4 passed in 0.05s

python -m json.tool \
  configs/evaluations/bidirectional_off_source_push_evaluator_v1.json
PASS
```

Proof class: `preregistered_bidirectional_off_source_push`.

No counted action was compiled. No robot motion, camera access, training, or
paid compute occurred.
