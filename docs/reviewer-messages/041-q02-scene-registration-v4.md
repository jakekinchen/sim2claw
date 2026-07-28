# Reviewer decision 041: Q02 scene registration v4

Date: 2026-07-27

Decision: `CONTINUE`

Evidence anchor: `100`

## Acceptance audit

- Q01 manifest identity verified before fit: pass.
- Only fit members opened by the fitter: pass.
- All eight D4 maps evaluated: pass.
- Board-center shift inside each `+/-80 mm` table-frame bound: pass.
- Board yaw unchanged: pass.
- Joint zeros unchanged because they are not separately identifiable: pass.
- Old config, scene IDs, and receipts unchanged: pass.
- CPU/fp64 MuJoCo scene rebuild and load: pass.
- Physical C2 body name preserved at transformed coordinate: pass.
- Canonical action NPY and raw float64 hashes unchanged: pass.
- Held-out semantic content opened: no.
- Robot motion, camera access, paid compute: none.

Candidate:
`configs/scenes/bidirectional_pawn_push_scene_registration_v4.json`.

Candidate SHA-256:
`c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b`.

Q03 may now open the frozen B7 held-out episode exactly once and must apply
the predeclared `25 mm` fit and held-out gates without tuning v4.
