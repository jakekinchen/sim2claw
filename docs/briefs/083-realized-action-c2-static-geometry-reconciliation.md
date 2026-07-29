# Brief 083 — Realized-Action C2 Static Geometry Reconciliation

Decision: `CONTINUE`

Evidence anchor: `102`

## Active card

C2 from the realized-action outcome calibration queue.

## Required slice

Compile existing evaluator-owned geometry evidence into one hash-bound,
read-only reconciliation:

- task-plane/board-corner residual;
- initial and terminal pawn-base residual;
- fixed-base robot residual;
- articulated keypoint residual;
- silhouette residual;
- any floor-height or support-plane residual.

Each channel must retain its own units, denominator, source, verdict, and proof
ceiling. A missing or rejected channel remains missing or rejected.

Preserve the accepted current task-plane mapping unless a held-out source
rejects it. Do not let camera pose absorb joint-zero/link error, and do not
open a joint optimizer.

## Verification gate

- Every reported number binds an existing immutable source.
- Board, pawn, base, articulation, silhouette, and floor/support are separate.
- Fit versus held-out provenance is visible.
- The D1 initial observation remains within its frozen 6 mm gate.
- No rejected geometry factor is promoted.
- A deterministic generated receipt and tracked closeout exist.
- Focused tests, workflow audit, and diff check pass.

## Handoff

On pass or honest partial, freeze C2-RP04N before any new annotation.
