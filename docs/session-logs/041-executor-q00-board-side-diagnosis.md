# Executor log 041: Q00 board-side diagnosis

Date: 2026-07-27

Decision: Q00 acceptance checks passed.

## Scope

- Read the immutable `701 x 6` C2 action.
- Compiled the exact `current_chess_scene` bound by the candidate manifest.
- Applied the manifest's frozen provisional transform under perfect tracking.
- Evaluated both the advisory end-effector-site observable and the
  task-relevant pad-gap/pawn-neck observable.
- Issued no robot, camera, network, or paid-compute command.

## Result

- Advisory site/base C2: `265.275519 mm`.
- Site/base C8: `80.897091 mm`.
- Site/base C7: `100.783880 mm`.
- Pad-gap/neck C2: `257.506340 mm`.
- Pad-gap/neck C8: `64.673854 mm`.
- Pad-gap/neck C7: `85.525518 mm`.
- C2-to-C8 board separation: `266.700000 mm`, exactly six squares.
- Independent direct-transform formula check: `PASS` at `1e-9 mm` absolute
  tolerance against all six primary values.

The categorical rank-side defect is confirmed. The advisory combined the
site/base C2 number with pad-gap/neck C8/C7 numbers, so its mixed triple is
not one consistent metric. The remaining corrected-side residual exceeds
`25 mm`; Q01 must freeze fit/held-out evidence before Q02 chooses a versioned
correction.

## Evidence

- `docs/run-logs/2026-07-27-bidirectional-pawn-push-q00-board-side-diagnosis.md`
- `docs/reviewer-messages/039-q00-board-side-diagnosis.md`

Proof class:
`read_only_action_frozen_perfect_tracking_fk_diagnostic`.
