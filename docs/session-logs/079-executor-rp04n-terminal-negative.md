# Session 079 — RP04N Terminal Negative

Date: `2026-07-29`

Decision: `CLOSE_RP04N_TERMINAL_NEGATIVE_ACTIVATE_C3`

## Result

The source, 18 sample indices, extraction, randomized two-pass annotation
orders, visibility gates, D1-only translation, simulator reference, and curve
thresholds were frozen at `dba0f57`. Both physical annotations were then
frozen at `cee2691` before the simulator pixel projection was opened.

Only samples `379`, `387`, and `395` exposed the selected pawn crown. The
gripper occluded the landmark through the rest of the carry. The immutable
evaluation therefore admitted `3 / 18` points versus the required `12 / 18`,
with temporal-tercile counts `[0,0,3]` and a maximum invalid run of `15`
versus the allowed `3`.

The sparse curve also failed the D1 translation, pointwise, and Fréchet gates.
The result is the terminal diagnostic negative
`camera_projected_carry_prefix_real_to_sim: 0/1`.

## Evidence

Generated ignored receipt:

- file: `outputs/rp04n_c922_crown_track_v1/receipt.json`;
- file SHA-256:
  `fd85934b5c00c455857232e96f4628d7f34a819058299f4e4f88728cc1cfe7d5`;
- artifact SHA-256:
  `cf1fbfff5d914b2a5fedff7825bcb3f89ef60a8001ab653e97bbc5f33a35bf0b`.

## Boundary

RP04N was action-free and adds no realized-action outcome evidence. No live
camera, gateway, serial, hardware, physical motion, physical attempt, or paid
compute was used. C3 is active.
