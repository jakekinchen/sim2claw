# Brief 086 — Realized-Action C3A First Divergence

Decision: `CONTINUE`

Evidence anchor: `105`

## Active card

C3A from the realized-action outcome calibration queue.

## Required slice

Build a deterministic, ordered first-divergence report for every frozen
episode:

1. initial geometry and mapping;
2. requested-to-sent transformation;
3. sent-to-measured joint response;
4. provisional end-effector projection;
5. first contact witness;
6. pawn planar motion;
7. lift or tip;
8. release or support;
9. final consequence.

Channels absent from an episode must be reported as unobservable, not passed.
Bind each observed divergence to its earliest sample and timestamp. Construct a
bounded sensitivity matrix for geometry, sample timing, actuation, contact, and
evaluator channels using only existing candidate replays and the C3 report.

## Verification gate

- Every episode has all nine ordered channels with observed, absent, or
  not-applicable status.
- The earliest observed divergence is deterministic and source-bound.
- Existing RP04K, RP04L, RP04M, and C3 evidence remains separate.
- Compensating or non-identifiable parameter pairs are flagged.
- Only a mechanism repeated outside the sealed episode may advance to C4/C5.
- A deterministic generated receipt and tracked closeout exist.
- Focused tests, workflow audit, and diff check pass.

## Handoff

Activate C4 with only the cross-episode temporal mechanisms admitted here.
