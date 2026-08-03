# OR69 — Renderer-native missing state-trace regeneration

Decision: `FOUR_EXACT_ACTION_REPLAYS_NO_PIXEL_ACCESS`

Evidence anchor: `OR68`

OR68 freezes all 11 episodes before renderer work and identifies exactly four
without published 3D state traces. Regenerate only those four with the immutable
cohort parameter vector and exact action identity.

## Required outcome

Run one existing MuJoCo replay for each missing recording ID. Emit one body-state
trace and one scene manifest per episode. Require the action hash, parameter
digest, historical diagnostic result fields, trace schema, finite body states,
and common scene revision to reproduce.

## Frozen constraints

- Physical sample metadata supplies actions; physical video paths and bytes are
  not read.
- One shared parameter vector; no episode override or candidate selection.
- Exactly four simulator replays and four traces.
- No renderer, image, video, metric, parameter fit, hardware, training,
  promotion, or transfer operation.

## Terminal rule

Pass only if all four traces reproduce under the frozen inputs and join the
same scene revision as the seven admitted traces. The result makes the state
corpus renderer-ready in provenance only. It establishes no renderer runtime,
camera, kinematic, event, physics, pixel-similarity, generalization, or transfer
claim.
