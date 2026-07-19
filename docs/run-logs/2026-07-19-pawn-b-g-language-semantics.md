# B-G Pawn Language Semantics Gate

Date: 2026-07-19 America/Chicago

## Outcome

The current product language surface is frozen as 12 directed brown-pawn
semantics: files B through G, ranks 1 and 2, in both directions. The contract
defines two deterministic training prompt forms and one development prompt
form without using an external model, archive material, outcome labels, or
held-out content.

This is a schema and leakage-control result, not a training result. There are
currently zero independently admitted current-geometry source groups and zero
training rows across this product surface. Prompt expansion cannot create
behavioral coverage, so a new paid GR00T run is not admitted by this gate.

## Frozen identities

- Language contract:
  `configs/tasks/pawn_b_g_language_semantics_v1.json`
- Language contract SHA-256:
  `8e1b1a863b02ce6f8ff2d446bfceda4202d35eb5e6346eb1988cf759b61eed8c`
- Product evaluator:
  `configs/evaluations/pawn_rank12_bidirectional_v2.json`
- Product evaluator SHA-256:
  `8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3`
- Product evaluator source commit:
  `36f1ebc5f66e63317b1fba84ba9aaabf66a5ff2d`
- Scene: `operator_updated_chess_workcell_v3`
- Workspace pose:
  `workspace_board_fiducial_robotward_100mm_20260718_v3`
- Board pose: `board_robotward_100mm_20260718_v3`

The validator rehashes the evaluator bytes and requires the exact ordered
semantic set, reverse pairs, target-coordinate authority, prompt templates,
provenance, source episode fields, receipt counts, and no-launch snapshot.

## Prompt and counting policy

The builder-facing training metadata renderer deterministically produces 24
task strings: two prompt forms for each of 12 semantics. These are metadata
rows only. They add zero independent episodes and zero independent behavioral
evidence.

Any future source data must be split by `source_episode_group_id` before prompt
expansion. Replays, camera copies, action-identical replicas, weighted copies,
and prompt variants from one source group remain in the same split. Held-out
rows may not enter the builder. Receipts must report source-group, source-
episode, prompt-derived, sampling-replica, and frame counts separately.

## Current blocker and next admissible step

The existing sparse simulation layout natively represents six of the 12
directions. A new clean-room source contract and reset/layout surface is needed
for the reverse directions. Each semantic then needs at least one independently
evaluator-admitted, current-geometry source group before a paid training run can
claim complete B-G behavioral coverage. The physical catalog contributes zero
training rows while replay, labels, and evaluator admission remain unresolved.

## Verification

- `uv run --frozen pytest -q tests/test_pawn_language_semantics.py`:
  21 passed;
- Python bytecode compilation: passed;
- JSON parse: passed;
- `git diff --check`: passed.

## Claim boundary

This gate proves only that the B-G task meaning, clean-room prompt provenance,
split order, evidence-counting rules, and current no-launch state are frozen and
internally consistent. It does not prove that training occurred, that a model
understands language, that any policy succeeds, that physics are calibrated,
that simulation transfers to the physical robot, or that physical motion is
authorized.
