# Session 078 — Realized-Action C2 Static Geometry

Date: `2026-07-29`

Decision: `PARTIAL_ACCEPT_C2_ACTIVATE_RP04N`

## Result

C2 reconciled six existing geometry channels without fitting:

- task plane: accepted at `4.7417 mm` RMS and `7.1043 mm` maximum;
- pawn base endpoints: accepted for endpoint observation only at `3.1006 mm`
  initial D1 and `3.3571 mm` terminal D2;
- fixed base: rejected as a camera constraint, with `44.9907 px` p90 and
  `0.1731` within four pixels;
- articulated differential: upper arm passes at `1.4318 px`, wrist fails at
  `5.1963 px` with negative correlation;
- robot silhouette: mid-pose median `10.6729 px` and p80 `21.8726 px` meet
  their numeric diagnostic gates, but the heldout was retrospectively
  inspected and the tag gate failed, so the result is not promotable;
- floor/support: visual board registration is `3.7586 px` over `166` held-out
  corners, but physical metric floor/support height residual is unavailable.

The accepted task plane is preserved. Global physical/model mapping remains
unapproved.

## Evidence

Generated ignored receipt:

- file:
  `outputs/realized_action_static_geometry_reconciliation_v1/receipt.json`;
- file SHA-256:
  `a2a66a99a7fb4412dc260a61e3cad6b5309565d2a5f02dcc7092d91d92d6089e`;
- artifact SHA-256:
  `db3104c720293076eaf4b30bf8ed3744ae35e5de7ce183c1902e8f6a48aa1f44`.

## Verification and boundary

- `uv run pytest tests/test_static_geometry_reconciliation.py -q` —
  `2 passed`.
- No camera, joint-zero, link, board, object, or floor parameter was fitted.
- No camera, gateway, serial, hardware, motion, pawn attempt, or paid compute
  was used.

C2-RP04N is active as an action-free camera diagnostic.
