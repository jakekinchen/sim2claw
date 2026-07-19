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

## Tracked Studio browser derivatives

Studio uses three byte-exact MP4 container derivatives because browsers do not
seek the source MKV containers consistently. Each derivative copies the
existing H.264 video stream without re-encoding, strips source metadata, and is
part of the tracked release contract rather than being authorized by the
ignored local integration receipt.

| Browser asset | Source asset / SHA-256 | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `replay-overhead-c922.browser.mp4` | `replay-overhead-c922.mkv` / `9278defb1a2dfdfbad1c465fe30305e680a15bc71b522ce3332f841b94557c9f` | 32,059,369 | `25ce9624194c0b36aaed5a6695327294eac1e34c5350b27d4aa118b88da34736` |
| `replay-side-logitech.browser.mp4` | `replay-side-logitech.mkv` / `dc840c46bc91ea760da052b51f114374c2ade7c5d45b05c69fde0cb2a5e63950` | 33,027,592 | `f852b64e2ae0fca8a23925641a03c0e4534379f66c4a4dd857fcae4baaa6d679` |
| `replay-wrist-d405.browser.mp4` | `replay-wrist-d405.mkv` / `19f2d6f853d8145ba1b6239b41cf31182778bc69e5bd4518069694af48780c2b` | 19,991,203 | `decb50a17c589640369785091e7c348b60d2264fd9d229e6c21bd60d6ec11f15` |

Derivation operation: `container_remux_h264_copy_to_mp4`. Producer identity:
FFmpeg 8.0.1, executable SHA-256
`0a96da2735695308d964e25fa6f4a0db2e9d24031390360f4c5ff96a4f8938e5`.
The ignored `studio-integration-receipt.json` may confirm and locate only these
three contracts; it cannot admit a filename, operation, producer, size, hash,
or source identity that is absent from or differs from the tracked JSON index.

## Proof boundary

This is evidence that a saved physical-teleoperation command trace was issued
through the guarded physical replay path and recorded from three viewpoints. It
is not evidence that a learned ACT checkpoint ran, that the chess move
succeeded, that object/contact dynamics were correct, or that the episode was
admitted to training. The operator's positive note belongs to the original
source recording and is not a separate evaluator result.

Use `PHYSICAL_REPLAY_RELEASE_20260719.json` for the machine-readable asset index
and `PHYSICAL_REPLAY_RELEASE_20260719.sha256` to verify downloaded assets.
