# Brief 088 — Realized-Action C5 Contact Identifiability

Decision: `CONTINUE`

Evidence anchor: `107`

## Active card

C5 from the realized-action outcome calibration queue.

## Required slice

Run a fail-closed contact/object identifiability gate before fitting anything:

- inventory fit and validation episodes for per-sample contact, metric object
  path, first-contact, lift/tip, release, and support witnesses;
- keep the sealed D1→D2 RP04K/RP04L result outside model selection;
- enumerate only parameter families whose observables exist in nonsealed data;
- preserve the current MuJoCo contact path as an unvalidated baseline when no
  family is identifiable;
- reject observed grasp/release markers, final-square loss, endpoint forcing,
  support projection, and unsupported force/current semantics as model inputs.

## Verification gate

- Every potential contact dimension is linked to a nonsealed observable or
  rejected.
- No sealed consequence selects a parameter.
- No contact model is promoted from missing evidence.
- The terminal negative, if reached, names exactly what new evidence is needed.
- A deterministic generated receipt and tracked closeout exist.
- Focused tests, workflow audit, and diff check pass.

## Handoff

Activate C6 with the C5 admission status visible. A C6 simulator outcome cannot
be promoted through an unvalidated contact model.
