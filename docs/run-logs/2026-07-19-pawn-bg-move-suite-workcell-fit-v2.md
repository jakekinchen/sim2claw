# Move-suite workcell fit v2: cross-file and diagonal test cases

Date: 2026-07-19 America/Chicago

## Why this lane exists

The v1 workcell fit reduced training-side event RMS from 309.55 mm to
17.41 mm and recovered repeatable selected-piece contact, but it constrained
the fit with 22 events from same-file rank moves only. Its two held-out
episodes (`d1-to-d2`, `g1-to-g2-redo`) are opened and burned as fresh
evidence, and its selected candidate carries an 18.70-degree shoulder-lift
zero offset flagged for independent audit.

The frozen catalog and sysid split already contain recorded physical moves
the v1 product-scope filter discarded:

| Recording | Move class | Split | Used by v1 |
| --- | --- | --- | --- |
| `b2-to-c2` | file (cross-file) | train | no |
| `d2-to-e2` | file (cross-file) | train | no |
| `e1-to-f1` | file (cross-file) | train | no |
| `d2-to-e1` | diagonal | train | no |
| `c1-to-d2` | diagonal | held out | no — never opened |

Cross-file and diagonal moves sweep the pinch point laterally across the
board, so their gripper-close/reopen events constrain board yaw and board
center far better than rank moves alone, and they exercise arm poses that
can distinguish the shoulder-lift offset from an unmodeled geometry error.
The never-opened diagonal held-out recording supports exactly one fresh
kinematic-generalization admission on a move class absent from v1 training.

## What was added

- `configs/optimization/pawn_bg_workcell_fit_v2.json` — frozen v2 contract:
  identical staged bounded parameterization and selection rule as v1, wider
  data scope, fresh held-out set defined as sysid held-out minus the two
  recordings v1 already opened, admission threshold unchanged at 60 mm with
  the no-clipping requirement.
- `src/sim2claw/pawn_bg_workcell_fit_v2.py` — move-suite scope (any
  `X-to-Y` square label, classified rank/file/diagonal with span), the v2
  fit and one-shot held-out runners, per-move-class kinematic breakdowns,
  and a diagnostic replay scorer for moves outside the frozen 12-skill
  reward table (same trace-row schema and frozen thresholds; no frozen gate
  verdict or task-success claim is emitted for them).
- CLI: `sim2claw pawn-bg-workcell-fit-v2` and
  `sim2claw pawn-bg-workcell-holdout-v2`.
- `tests/test_pawn_bg_workcell_fit_v2.py` — eight focused tests: contract
  authority stays fully non-authorizing, schema drift fails closed, move
  classification, cross-file/diagonal scope admission, destination-occupancy
  flagging, replay-support guard for files without a baseline piece,
  minimum-scope fail-closed, and the frozen catalog/split resolving to the
  expected 15-train / 1-fresh-held-out scope.

## Board-state honesty for replays

Replays place only the selected piece at the recorded source square. Three
cross-file recordings end on squares occupied by a different baseline piece
(`b2-to-c2`, `d2-to-e2`, `e1-to-f1`); their physical board state is not
modeled, so they are flagged `baseline_destination_square_occupied` and
summarized separately. They still contribute fully to the kinematic event
fit, which involves no pieces.

## How to run (requires the physical source assets)

The hash-bound `datasets/manipulation_source_recordings/` assets are not in
this Git history, so the fit must run on a machine that has them:

```bash
uv run sim2claw pawn-bg-workcell-fit-v2 \
  --source-repository-root /path/to/source/repo \
  --output outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v2/fit_receipt.json

# only after reviewing the receipt and freezing the candidate:
uv run sim2claw pawn-bg-workcell-holdout-v2 \
  --source-repository-root /path/to/source/repo \
  --receipt outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v2/fit_receipt.json \
  --output outputs/pawn_bg_act_v1/pawn_bg_workcell_fit_v2/held_out_validation.json
```

The fit uses 15 training recordings (30 events) instead of 11 (22 events).
Expected outcomes worth reading off the receipt:

1. `kinematic_by_move_class` — if the rank-move RMS stays near 17 mm while
   file/diagonal RMS is much larger, the v1 candidate was overfitted to the
   rank geometry and the board-pose or shoulder-lift explanation needs
   revision. If all classes fit comparably, the candidate generalizes.
2. The stage-D shoulder-lift offset refitted under lateral constraints — a
   materially different value is evidence the 18.70 degrees was compensating
   for something else.
3. The fresh diagonal held-out admission at the unchanged 60 mm bound.

## Growing the test-case suite (recording protocol)

The harness picks up new physical recordings without code changes. To add a
test case of moving one piece anywhere on the board:

1. Record the teleoperated move with the existing recorder; name the folder
   `<source>-to-<destination>` (for example `b1-to-e2`, `c2-to-f1`, or a
   full-span `b1-to-g2`). Diagonal and long-span moves add the most fit
   leverage; spans above one square are currently absent from the data.
2. Append the recording to
   `configs/data/physical_pawn_move_catalog_20260719.json` (or a successor
   catalog) with its hash bindings.
3. Assign it to `train` or `held_out` in the sysid split BEFORE looking at
   any fit output, and never move it afterwards. New held-out recordings are
   the only way to mint fresh admission evidence; the v1 pair stays burned
   and `c1-to-d2` burns the moment the v2 holdout command runs.
4. Re-run the fit command above. Squares on files a/h participate in the
   kinematic fit but are skipped by consequence replay until the sparse
   scene grows a piece for that file.

## Claim boundary

Nothing in this lane grants training, policy, promotion, physical-motion,
or physical-calibration authority. Event RMS is a simulator-frame kinematic
fit metric, not sim-to-real error; replay consequence metrics are
diagnostic. The v1 receipt and its ledger rows remain the frozen record of
the rank-move progression.
