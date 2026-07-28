# Brief 054 — Phase A real-to-sim task transfer

## Outcome

Publish one reviewer-visible Studio episode for a visually verified physical
pawn transfer before any simulator-to-real motion is considered.

## Boundaries

- Select between the fresh B5→A5 and D1→D2 operator recordings by inspecting
  their actual C922 and D405 media.
- Preserve raw source metadata without correction.
- Keep recorded reality, observed-joint visual reconstruction, and
  action-frozen physics as separate lanes.
- Fail the physics lane closed if exact command and timing lineage cannot be
  established. Do not add retiming, clipping, IK, offsets, interpolation
  repair, action assistance, or corrective suffixes.
- Use the existing Studio episode flow and existing comparison receipt schema.
- Do not touch hardware in this phase.

## Acceptance

- A browser-playable comparison is admitted by the Studio catalog.
- The physical D1→D2 outcome is visible from source media.
- The observed-joint twin is hash-bound and explicitly non-physical.
- The action-frozen physics lane either runs identically or displays its exact
  fail-closed blocker.
- A binary evaluator-owned receipt and concise run log bind the result.
