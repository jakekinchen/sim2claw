# Bidirectional Pawn-Push V2 Orientation Migration Goal Loop

## Mission

Make the standard physical chessboard frame explicit before any further V05-UG
work: rank 1 is nearest the operator and board-reaching left arm, rank 8 is
farthest, and all new square-dependent work crosses one reviewed adapter to the
immutable 180-degree-rotated legacy scene frame.

## Source of truth

1. Owner instruction defining the standard near/far convention.
2. `AGENTS.md`.
3. The current physical-layout capture configuration and owner-reviewed
   landmark diagnosis in `src/sim2claw/pawn_bg_workcell_fit.py`.
4. The canonical orientation contract and migration ledger produced by this
   loop.
5. Historical receipts, actions, hashes, and scene registrations, preserved
   byte-for-byte in their original frame.
6. Advisory-model feedback, which cannot grant execution authority.

## Intended outcome

The repository has one test-covered, bijective `rotate_180` adapter, an exact
metric/frame contract, a migration ledger that distinguishes historical and
active labels, a responsive Studio board with every canonical coordinate and
near/far cues visible, and a queue/graph state that is paused for Fable review.
V05-UG cannot enumerate or load a model while paused.

## Acceptance criteria

- Physical near side is tied to the current left-arm/table landmark, not an
  image-only guess.
- All 64 legacy/canonical mappings are bijective and self-inverse.
- The global legacy-to-canonical transform is `rotate_180`; the historical
  V04 `reflect_ranks` fit-only candidate is not reinterpreted.
- Historical receipts, raw labels, action bytes, and hashes remain unchanged.
- V05-UG is fail-closed with model, simulation, camera, gateway, serial,
  physical, promotion, and transfer authority all false.
- Studio shows all 64 canonical labels and explicit rank-1-near/rank-8-far
  cues on desktop and mobile.
- Focused contract, mapping, UI, graph, and pause tests pass.
- Queue and graph end at
  `PAUSED_ORIENTATION_MIGRATION_COMPLETE_AWAITING_FABLE`, with resume false.

## Evidence standard

Record changed paths and hashes, focused test output, a deterministic rendered
board artifact inspected at desktop and mobile dimensions, graph validation,
the scoped commit, pushed branch, and any unresolved blocker. Never call this
transfer proof or physical calibration.

## Decision status

- Confirmed: standard rank 1 near; current scene labels rank 8 near; physical
  and legacy scene labels differ by 180 degrees.
- Confirmed: no enumeration, model load, dynamic work, paid compute, camera,
  gateway, serial, or hardware action during this migration.
- Default: preserve historical square IDs and add explicit canonical aliases.
- Open: Fable review may recommend the next prospectively frozen successor,
  but cannot retroactively alter this migration evidence.

## Execution rhythm

1. Inspect the live checkout, frame landmarks, and existing draft hashes.
2. Choose the smallest remaining acceptance criterion.
3. Implement without opening execution authority.
4. Record hashes, tests, and visual evidence.
5. Compare the result with every acceptance criterion.
6. Continue until complete or an evidence-backed blocker requires owner input.

## Progress ledger

Current state: `PAUSED_ORIENTATION_MIGRATION_COMPLETE_AWAITING_FABLE`.

Completed: physical near-side landmark and exact 180-degree raw-grid mapping
derived; semantic body/task IDs distinguished and preserved; pre-migration
draft hashes recorded; contract, ledger, fail-closed pause, Studio reference,
tests, visual inspection, queue, and both graph copies completed.

Evidence: current board center `(0.04, -0.065)` and left-arm mount
`(-0.04, +0.365)` in table XY; owner-reviewed sparse-row diagnosis;
`brown_pawn_b1 == canonical b1 == raw grid g8`; focused suite `31 passed`;
generated graph digest `3671a77a...`.

Remaining: scoped commit, push, and parent handoff to the existing Fable
thread.

Blockers: none.

Next step: commit/push intended paths only, then request Fable feedback.
