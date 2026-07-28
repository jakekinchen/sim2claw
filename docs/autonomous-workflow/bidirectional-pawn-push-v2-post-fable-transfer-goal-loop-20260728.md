# Bidirectional Pawn-Push V2 Post-Fable Transfer Goal Loop

## Mission

Close the current-task scene/label mismatch, then run one bounded prospective
low-planar static and temporal campaign to either obtain two robust families
per direction or produce the strongest honest terminal-negative claim before
the application deadline.

## Source of truth

1. Owner instructions and `AGENTS.md`.
2. The live branch, task queue, current graph, and immutable receipts.
3. The canonical board-orientation and current-task scene/label contracts.
4. Fable 5 feedback as advisory input only.
5. Prospective evaluator-owned static and temporal receipts.

## Milestone A — current-task contract wiring

Acceptance:

- Semantic body/task IDs remain canonical.
- Raw sparse-layout placement uses `rotate_180` exactly once.
- Source/destination target centers use `canonical_square_center` exactly once.
- Every compiled reset-layout pawn body must equal its canonical source center
  in XY within `1e-9 m` before action compilation.
- New versioned adapters target the V05 temporal-static path and terminal
  static implementation reached by the paused V05-UG wrapper while preserving
  all frozen implementation bytes.
- V04 `reflect_ranks` operations require explicit fit-only opt-in.
- Structure-only tests, graph compilation, and workflow audit pass.
- Milestone A is committed and pushed separately before any model load.

Current status: `IN_PROGRESS_AUDIT_PENDING`.

Execution authority: false for model loading, enumeration, simulation, dynamic
replay, camera, gateway, serial, physical motion, paid compute, promotion, and
transfer claims.

## Milestone B — one bounded prospective successor

Create a new versioned contract; never edit or execute the frozen paused
V05-UG contract. Preserve the exact 20-case quarantine, `36.025 mm` progress
gate, `<=2 mm` lift gate, two-family-per-direction requirement, direct-target
baseline, diagnostic `0.11 s` ZOH path, and physical authority false.

Freeze approximately six initial low-planar families using only prospective
static reachability, IK, collision, camera, and gateway margins. Geometry is
`18 mm` contact height, `16 mm` contact offset, `90 mm` stroke, and zero
vertical rise. Freeze the rank criterion before dynamics. At most one flat,
closed-jaw side/back anti-wedge hedge may be specified prospectively.

Run static first. Run temporal dynamics only when static admits at least two
families in each direction. Stop at the first frozen `2+2`.

Stop conditions:

- If static admits fewer than `2+2`, close a static terminal negative.
- If temporal admits fewer than two in either direction, close a temporal
  terminal negative, prohibit V05-UH/V05-UI successors before the deadline,
  and report the strongest surviving directional claim.
- If temporal admits `2+2`, stop before camera or physical work. The next gate
  is task-plane registration `<=25 mm`, with at most one recapture. Fable's
  `50–130 mm` range remains advisory only.

## Loop rhythm

1. Keep exactly one active milestone.
2. Freeze inputs and ranking before opening outcomes.
3. Record hashes and authority at each checkpoint.
4. Run only the checks authorized by the active milestone.
5. Update the queue and graph from receipts.
6. Stop on the first acceptance or terminal-negative condition.

## Checkpoints

- A audit/design: complete.
- A implementation/tests: complete; graph/workflow audit pending.
- A commit/push: pending.
- B prospective freeze: blocked until A commit/push.
- B static: blocked until B freeze.
- B temporal/final: blocked until static `2+2`.

Unrelated user-owned files remain out of scope, including
`tools/build_fiducial_sheet.py`.
