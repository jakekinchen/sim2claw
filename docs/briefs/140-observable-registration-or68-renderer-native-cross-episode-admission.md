# OR68 — Renderer-native cross-episode admission

Decision: `FREEZE_ALL_ELEVEN_EPISODES_BEFORE_RENDERER_WORK`

Evidence anchor: `OR67_QUARANTINE`

OR67 crossed the episode-specific pixel gates with target-derived screen-space
vectors, not a 3D renderer. Preserve that receipt as a proxy pass and exclude
its candidate artifacts from every successor candidate input.

## Required outcome

Inventory all 11 action-frozen physical recordings in the immutable group-probe
cohort. Deterministically hash-sort recording IDs into 4 development, 3
validation, and 4 evaluator-heldout episodes. Verify the physical videos,
sample traces, action identities, shared 3D scene, and available published state
traces. Report missing trace regeneration work without running simulation.

## Frozen constraints

- Decode zero physical frames and emit JSON only.
- Historical outcome rank cannot affect the split.
- A physical video may be byte-hashed but cannot construct any candidate.
- OR63, OR66, and OR67 screen-space artifacts are prohibited candidate inputs.
- No renderer, simulator replay, parameter fit, candidate video, hardware,
  heldout opening, training, promotion, or transfer claim.

## Terminal rule

Pass the admission slice only if the 11 recording and action identities are
distinct, every physical video and sample trace exists, the deterministic split
is complete, every published trace verifies against one shared scene, and the
missing-trace count is explicit. A pass freezes the successor lane; it does not
claim renderer readiness, pixel similarity, kinematic/event/physics fidelity,
prospective generalization, or transfer.
