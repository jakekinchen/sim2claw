# Reviewer decision 043: Q04 immutable C2 replay under v4

Date: 2026-07-27

Decision: `CONTINUE`

Evidence anchor: `100`

## Acceptance audit

- Immutable NPY SHA-256 unchanged: pass.
- Immutable raw float64 SHA-256 unchanged: pass.
- Native CPU/fp64, 40 Hz, five-step replay: pass.
- Old/v4 metrics shown side by side: pass.
- First physical/simulator divergence explicit: pass.
- Selected and wrong-piece contact counts explicit: pass.
- Post-outcome and no-promotion labels explicit: pass.
- V4 task consequence: fail, preserved as evidence.
- Robot motion, camera access, paid compute: none.

Receipt:
`runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json`.

SHA-256:
`36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664`.

Q05 may preregister only the already reduced F1 off-source consequence. It
must not use Q04 to claim v4 admission or destination-square placement.
