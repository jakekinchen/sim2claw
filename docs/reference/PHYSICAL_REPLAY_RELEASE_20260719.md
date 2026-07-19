# Physical replay evidence release — 2026-07-19 UTC

Private GitHub Release: `physical-replay-evidence-20260719`

This release groups the diagnostic video for source episode
`20260718T230416Z-573f2320` with three camera views captured while that episode's
recorded command trace was replayed through the guarded physical gateway. The
large media files and generated receipts are GitHub Release assets; they are not
stored in Git history.

## Source episode

- Display label: `F 2 to f 1`
- Operator note: `That's cool. Pass with flying colors.`
- Structured receipt metadata: brown pawn `e2` to `e1`
- Proof class: `physical_teleoperation_source_unqualified`
- Training status: not training data; admission remains pending deterministic
  replay and a separate evaluator

The display label and structured square metadata disagree. Both are preserved
verbatim so a reviewer can resolve the annotation rather than silently changing
the record.

## Replay capture

- Replay run: `20260719T010448Z-20260718T230416Z-573f2320-8e655391`
- Status: completed; follower torque was off after shutdown
- Samples: 243 completed, 233 exact-command samples, 51 samples reported as
  safety-clamped
- Camera alignment: creation-time alignment with an estimated uncertainty of
  1.0 second; use each camera's replay-window offsets in the capture receipt
- Views: C922 overhead, Logitech side, and D405 wrist/gripper-upward

The D405 asset is ordinary visible diagnostic video. It does not establish
metric depth, intrinsics, hand-eye calibration, or task success.

## Proof boundary

This is evidence that a saved physical-teleoperation command trace was issued
through the guarded physical replay path and recorded from three viewpoints. It
is not evidence that a learned ACT checkpoint ran, that the chess move
succeeded, that object/contact dynamics were correct, or that the episode was
admitted to training. The operator's positive note belongs to the original
source recording and is not a separate evaluator result.

Use `PHYSICAL_REPLAY_RELEASE_20260719.json` for the machine-readable asset index
and `PHYSICAL_REPLAY_RELEASE_20260719.sha256` to verify downloaded assets.
