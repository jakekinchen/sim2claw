# Brief 082 — Realized-Action C1 EpisodeTwinBundle

Decision: `CONTINUE`

Evidence anchor: `101`

## Active card

C1 from
`docs/autonomous-workflow/realized-action-outcome-calibration-task-queue-20260729.md`.

## Required slice

Build a deterministic `EpisodeTwinBundle.v1` for each of the four fit, three
validation, and one sealed C0 episodes.

Each bundle must bind:

- raw receipt and sample file hashes;
- requested, gateway-sent, measured-joint, and source-timestamp tensors;
- declared dtypes, units, joint order, sample count, and source time origin;
- asset and task-label provenance from C0;
- first requested, sent, and measured row exactly;
- initial pawn observation only when an evaluator-owned current-canonical
  physical observation exists;
- every missing observable explicitly.

The sealed bundle may bind the RP04M initial D1 metric observation and its
mapping residual, but not the terminal D2 observation as replay input.

## Verification gate

- Eight bundles are emitted.
- A second build is byte- and digest-identical.
- Every tensor digest matches C0.
- The first measured and first sent rows round-trip exactly.
- Units and time origins are explicit.
- No actuator application time, force, contact, depth, hidden pawn pose, or
  terminal endpoint is imputed.
- A tracked closeout binds the generated ignored receipt/bundles.
- Focused tests, workflow audit, and diff check pass.

## Handoff

On pass, close C1 and activate C2. On a missing observable, preserve it as
missing and continue unless the bundle cannot bind its actual source.
