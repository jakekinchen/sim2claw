# Session 084 — Realized-Action C6 Terminal Negative

Date: `2026-07-29`

Decision: `TERMINAL_C6_NEGATIVE_ACTIVATE_C7`

## Result

The one write-once C6 replay consumed the exact physical gateway-sent
`531 x 6` float32 tensor through C4's validated effective joint plant. It used
only measured robot row zero and the frozen physical C922 D1 initialization.
No later observed state, grasp/release marker, camera update, endpoint, latch,
support projection, clipping, IK, offset, or action repair was consumed.

Natural current-MuJoCo contact did not reproduce the physical grasp/carry. The
pawn remained essentially at D1 through sample `385`, began moving at `386`,
and was launched at sample `388`. It settled `69.148 mm` from D2, inverted at
`179.992 deg`, `31.947 mm` above its initial support height, while an exclusion
moved `31.570 mm`. Numerical and promotable success are both false.

## Evidence

Generated ignored receipt:

- file: `outputs/realized_action_outcome_mission_v1/receipt.json`;
- file SHA-256:
  `4bcf1f1a6c389c61fb1eb1445afd20ab0be814eb1cbaee13ad2d11e0198587d4`;
- artifact SHA-256:
  `df3f6abab728ec6a74a468afeb531b4bec99346c693ec081786c8dd8fb8c2c38`.

The ledger is
`realized_gateway_sent_action_trajectory_real_to_sim: 0/1`.

## Boundary

C3A admitted no untested cross-episode contact mechanism and C5 found no
nonsealed contact/object witnesses, so no successor is admitted. C7 is active;
it cannot revise C6.
