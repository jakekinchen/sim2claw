# Goal-Conditioned ACT Contract Gate

Date: 2026-07-18 America/Chicago

Git baseline before implementation: `4cd52bc`

## Frozen identity

- Contract: `configs/tasks/chess_pick_place_act_state_v1.json`
- Schema: `sim2claw.chess_pick_place_act_state_task.v1`
- SHA-256: `3f1fcdbbe6dcd552e1261af4713ac80734ca394854d196e61a26a1934d4166b5`
- Observation: 61 values in the frozen declared feature order
- Action: six clipped absolute SO-101 joint-position targets
- Training rows created by this gate: zero
- Held-out training rows: zero
- Physical source layout: brown pawns at A2, B1, C2, D1, E2, F1, G2, and H1
- Far-side layout: tan pawns at A8, B7, C8, D7, E8, F7, G8, and H7
- Supported-first grasp family: pawn-like small base

The contract was retargeted to the owner-confirmed pawn layout before any M7
training row or checkpoint existed. Its predecessor hashes and 61-by-6 feature
and action dimensions remain unchanged.

Frozen predecessors remained byte-identical:

- `chess_rook_lift_v1.json`: `cbd590e144b5b2a7d3c2a520ed76334bc0696b6e25003290e90a7064aca21587`
- `chess_pick_place_groot_v1.json`: `988a5a93d26358770c2dc3731602ba1dc11f723974758659d4cb05392f63ef58`

## Validation

`tests/test_act_pick_place.py` passed 9 tests and 10 declared negative
subtests. Fixtures covered exact dimensions/order, continuous target encoding,
prohibited progress/time and square leakage, invalid frames, split overlap,
lineage completeness, evaluator rejection classes, action ownership, and zero
assistance.

The gate created no dataset, checkpoint, learned-policy result, hardware
authority, or physical task evidence. M7 remains responsible for source
segmentation, retargeting, full MuJoCo replay, and strict-success admission.
